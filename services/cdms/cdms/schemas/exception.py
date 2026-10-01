class NotFoundError(Exception):
    pass


class NormalizationError(ValueError):
    pass


class InventoryUnavailable(RuntimeError):
    pass


class PageCapExceeded(InventoryUnavailable):
    pass
