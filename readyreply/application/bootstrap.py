"""Make sure the business and its built-in variables exist (F11-06)."""

from readyreply.application.ports import BusinessResolver, UnitOfWorkFactory
from readyreply.domain.variables import builtin_variables


class EnsureBusiness:
    def __init__(
        self, uow_factory: UnitOfWorkFactory, business: BusinessResolver, locale: str
    ) -> None:
        self._uow_factory = uow_factory
        self._business = business
        self._locale = locale

    def execute(self) -> None:
        business_id = self._business.current()
        with self._uow_factory() as uow:
            if uow.businesses.ensure(business_id, self._locale):
                uow.variables.replace_all(business_id, builtin_variables())
            uow.commit()
