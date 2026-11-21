"""Make sure the single v1 business and its built-in variables exist (F11-06)."""

from readyreply.application.auth import BUSINESS_ID
from readyreply.application.ports import UnitOfWorkFactory
from readyreply.domain.variables import builtin_variables


class EnsureBusiness:
    def __init__(self, uow_factory: UnitOfWorkFactory, locale: str) -> None:
        self._uow_factory = uow_factory
        self._locale = locale

    def execute(self) -> None:
        with self._uow_factory() as uow:
            if uow.businesses.ensure(BUSINESS_ID, self._locale):
                uow.variables.replace_all(BUSINESS_ID, builtin_variables())
            uow.commit()
