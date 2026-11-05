"""Immutable provider selection for one CLI process/session."""
from dataclasses import dataclass

from services.llm_client import PROVIDER_LABELS, get_model_provider


@dataclass(frozen=True)
class ProviderSession:
    provider: str

    def __post_init__(self):
        if self.provider not in PROVIDER_LABELS:
            raise ValueError("Nieznany provider sesji.")

    @property
    def label(self) -> str:
        return PROVIDER_LABELS[self.provider]

    def models(self, models: dict[str, str]) -> dict[str, str]:
        return {label: model for label, model in models.items()
                if get_model_provider(model) == self.provider}

    def validate_model(self, model: str) -> None:
        if get_model_provider(model) != self.provider:
            raise ValueError("Provider sesji jest stały. Zmiana wymaga ponownego uruchomienia aico.")
