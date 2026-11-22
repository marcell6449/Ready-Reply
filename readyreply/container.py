"""Composition root: the only place that connects concrete classes to ports."""

from dataclasses import dataclass
from datetime import timedelta

import httpx
from sqlalchemy import Engine

from readyreply.application import (
    ai,
    answers,
    auth,
    copying,
    csv_transfer,
    demo,
    search,
    stats,
    synonyms,
    unanswered,
    users,
    variables,
)
from readyreply.application.bootstrap import EnsureBusiness
from readyreply.application.ports import UnitOfWorkFactory
from readyreply.config import LOCALES, Settings
from readyreply.domain.ai import PromptTemplate
from readyreply.domain.search.engine import SearchEngine
from readyreply.domain.search.scorers import (
    ExactScorer,
    FuzzyScorer,
    PrefixScorer,
    Scorer,
    SynonymScorer,
)
from readyreply.domain.search.stopwords import STOP_WORDS
from readyreply.domain.search.tokens import Tokenizer
from readyreply.domain.unanswered import QuestionKeyer
from readyreply.domain.variables import BUILTIN_KEYS
from readyreply.infrastructure.ai.manual_prompt import ManualPromptProvider
from readyreply.infrastructure.ai.registry import build_provider
from readyreply.infrastructure.clock import SystemClock
from readyreply.infrastructure.csv.codec import StandardCsvCodec
from readyreply.infrastructure.db.engine import make_engine, make_session_factory
from readyreply.infrastructure.db.unit_of_work import SqlUnitOfWork
from readyreply.infrastructure.demo.catalog import JsonDemoCatalog
from readyreply.infrastructure.search.distance import RapidfuzzDistance
from readyreply.infrastructure.security.memory import MemoryLoginFailureLog, MemoryRepeatGuard
from readyreply.infrastructure.security.passwords import Argon2PasswordHasher
from readyreply.infrastructure.security.tokens import SecureTokenService
from readyreply.infrastructure.texts import TranslationTexts


@dataclass(frozen=True)
class AuthUseCases:
    needs_setup: auth.NeedsSetup
    setup: auth.SetupFirstAdmin
    login: auth.Login
    logout: auth.Logout
    resolve: auth.ResolveSession


@dataclass(frozen=True)
class ContentUseCases:
    list_variables: variables.ListVariables
    update_variables: variables.UpdateVariables
    list_answers: answers.ListAnswers
    create_answer: answers.CreateAnswer
    edit_answer: answers.EditAnswer
    delete_answer: answers.DeleteAnswer
    duplicate_answer: answers.DuplicateAnswer
    list_synonyms: synonyms.ListSynonyms
    update_synonyms: synonyms.UpdateSynonyms
    search: search.SearchAnswers
    copy: copying.CopyAnswer


@dataclass(frozen=True)
class ActivityUseCases:
    record_unanswered: unanswered.RecordUnanswered
    list_unanswered: unanswered.ListUnanswered
    dismiss_unanswered: unanswered.DismissUnanswered
    answer_question: unanswered.AnswerQuestion
    stats: stats.GetStats
    suggest: ai.SuggestAnswer


@dataclass(frozen=True)
class AdminUseCases:
    list_users: users.ListUsers
    create_user: users.CreateUser
    update_user: users.UpdateUser
    delete_user: users.DeleteUser
    export_csv: csv_transfer.ExportAnswers
    import_csv: csv_transfer.ImportAnswers
    load_demo: demo.LoadDemo


@dataclass(frozen=True)
class Container:
    settings: Settings
    engine: Engine
    http_client: httpx.Client
    bootstrap: EnsureBusiness
    auth: AuthUseCases
    content: ContentUseCases
    activity: ActivityUseCases
    admin: AdminUseCases


def _prompt_settings(texts: TranslationTexts) -> ai.PromptSettings:
    template = PromptTemplate(
        intro=texts.text("server.ai.intro"),
        variables_heading=texts.text("server.ai.variables"),
        titles_heading=texts.text("server.ai.titles"),
        question_heading=texts.text("server.ai.question"),
        rules=texts.text("server.ai.rules"),
    )
    labels = {key: texts.text(f"var.{key}") for key in BUILTIN_KEYS}
    return ai.PromptSettings(template, texts.text("server.ai.language"), labels)


@dataclass(frozen=True)
class _Shared:
    """Infrastructure objects shared by several use cases."""

    settings: Settings
    uow: UnitOfWorkFactory
    clock: SystemClock
    texts: TranslationTexts
    hasher: Argon2PasswordHasher
    tokens: SecureTokenService
    guard: MemoryRepeatGuard
    tokenizer: Tokenizer
    http_client: httpx.Client
    create_answer: answers.CreateAnswer

    @property
    def ttl(self) -> timedelta:
        return timedelta(hours=self.settings.session_hours)


def _auth(shared: _Shared) -> AuthUseCases:
    starter = auth.SessionStarter(shared.tokens, shared.clock, shared.ttl)
    failures = MemoryLoginFailureLog()
    return AuthUseCases(
        needs_setup=auth.NeedsSetup(shared.uow),
        setup=auth.SetupFirstAdmin(shared.uow, shared.hasher, starter),
        login=auth.Login(shared.uow, shared.hasher, failures, starter, shared.clock),
        logout=auth.Logout(shared.uow, shared.tokens),
        resolve=auth.ResolveSession(shared.uow, shared.tokens, shared.clock, shared.ttl),
    )


def _search(shared: _Shared) -> search.SearchAnswers:
    scorers: list[Scorer] = [
        ExactScorer(),
        SynonymScorer(),
        PrefixScorer(),
        FuzzyScorer(RapidfuzzDistance()),
    ]
    engine = SearchEngine(shared.tokenizer, scorers)
    return search.SearchAnswers(shared.uow, engine, search.SearchIndexCache(shared.tokenizer))


def _content(shared: _Shared) -> ContentUseCases:
    suffix = shared.texts.text("server.copy_suffix")
    return ContentUseCases(
        list_variables=variables.ListVariables(shared.uow),
        update_variables=variables.UpdateVariables(shared.uow),
        list_answers=answers.ListAnswers(shared.uow),
        create_answer=shared.create_answer,
        edit_answer=answers.EditAnswer(shared.uow, shared.clock),
        delete_answer=answers.DeleteAnswer(shared.uow),
        duplicate_answer=answers.DuplicateAnswer(shared.uow, shared.create_answer, suffix),
        list_synonyms=synonyms.ListSynonyms(shared.uow),
        update_synonyms=synonyms.UpdateSynonyms(shared.uow),
        search=_search(shared),
        copy=copying.CopyAnswer(shared.uow, shared.clock, shared.guard),
    )


def _suggest(shared: _Shared) -> ai.SuggestAnswer:
    provider = build_provider(shared.settings, shared.http_client)
    fallback = ManualPromptProvider(shared.settings.ai_chat_url)
    by_locale = {locale: _prompt_settings(TranslationTexts(locale)) for locale in LOCALES}
    return ai.SuggestAnswer(shared.uow, provider, fallback, by_locale, shared.settings.locale)


def _activity(shared: _Shared) -> ActivityUseCases:
    keyer = QuestionKeyer(shared.tokenizer)
    return ActivityUseCases(
        record_unanswered=unanswered.RecordUnanswered(
            shared.uow, keyer, shared.clock, shared.guard
        ),
        list_unanswered=unanswered.ListUnanswered(shared.uow),
        dismiss_unanswered=unanswered.DismissUnanswered(shared.uow),
        answer_question=unanswered.AnswerQuestion(shared.uow, shared.create_answer),
        stats=stats.GetStats(shared.uow),
        suggest=_suggest(shared),
    )


def _admin(shared: _Shared) -> AdminUseCases:
    codec = StandardCsvCodec()
    max_bytes = shared.settings.max_csv_bytes
    return AdminUseCases(
        list_users=users.ListUsers(shared.uow),
        create_user=users.CreateUser(shared.uow, shared.hasher),
        update_user=users.UpdateUser(shared.uow, shared.hasher),
        delete_user=users.DeleteUser(shared.uow),
        export_csv=csv_transfer.ExportAnswers(shared.uow, codec),
        import_csv=csv_transfer.ImportAnswers(shared.uow, codec, shared.create_answer, max_bytes),
        load_demo=demo.LoadDemo(shared.uow, JsonDemoCatalog(), shared.create_answer),
    )


def build_container(settings: Settings) -> Container:
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    def uow_factory() -> SqlUnitOfWork:
        return SqlUnitOfWork(session_factory)

    clock = SystemClock()
    shared = _Shared(
        settings=settings,
        uow=uow_factory,
        clock=clock,
        texts=TranslationTexts(settings.locale),
        hasher=Argon2PasswordHasher(),
        tokens=SecureTokenService(),
        guard=MemoryRepeatGuard(),
        tokenizer=Tokenizer(STOP_WORDS),
        http_client=httpx.Client(timeout=settings.ai_timeout_seconds),
        create_answer=answers.CreateAnswer(uow_factory, clock),
    )
    return Container(
        settings=settings,
        engine=engine,
        http_client=shared.http_client,
        bootstrap=EnsureBusiness(uow_factory, settings.locale),
        auth=_auth(shared),
        content=_content(shared),
        activity=_activity(shared),
        admin=_admin(shared),
    )
