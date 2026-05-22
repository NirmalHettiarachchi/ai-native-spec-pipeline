from importlib import import_module
from pathlib import Path

_SOURCE_PACKAGE = Path(__file__).resolve().parent / "src" / "demo_app"
__path__.append(str(_SOURCE_PACKAGE))

__all__: list[str] = []


def _export(module_name: str, names: tuple[str, ...]) -> None:
    if not (_SOURCE_PACKAGE / f"{module_name}.py").exists():
        return
    module = import_module(f".{module_name}", __name__)
    for name in names:
        if hasattr(module, name):
            globals()[name] = getattr(module, name)
            __all__.append(name)


_export(
    "discount_calculator",
    ("DiscountValidationError", "calculate_discounted_price"),
)
_export("scientific_calculator", ("CalculatorError", "run_scientific_calculator"))
