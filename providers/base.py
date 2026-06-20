# Базовый интерфейс источника «что играет сейчас».


class Provider:
    # Человекочитаемое имя источника (для статуса в GUI)
    name = "base"

    def get_now_playing(self) -> str | None:
        """Возвращает строку 'Исполнитель — Трек' или None, если ничего не играет."""
        raise NotImplementedError
