from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScreenRect:
    x: int
    y: int
    width: int
    height: int

    @property
    def left(self) -> int:
        return self.x

    @property
    def top(self) -> int:
        return self.y

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    @classmethod
    def from_rect(cls, rect) -> "ScreenRect":
        return cls(x=rect.x(), y=rect.y(), width=rect.width(), height=rect.height())


def choose_screen(screens: list[ScreenRect], point: tuple[int, int]) -> ScreenRect:
    if not screens:
        raise ValueError("at least one screen is required")

    for screen in screens:
        if _contains(screen, point):
            return screen

    return min(screens, key=lambda screen: _distance_to_rect_squared(screen, point))


def top_right_position(screen: ScreenRect, size: tuple[int, int]) -> tuple[int, int]:
    width, height = size
    max_x = max(screen.left, screen.right - width)
    max_y = max(screen.top, screen.bottom - height)
    return (max_x, min(screen.top, max_y))


def panel_position(
    anchor_rect: ScreenRect,
    panel_size: tuple[int, int],
    screen: ScreenRect,
) -> tuple[int, int]:
    panel_width, panel_height = panel_size
    desired_x = anchor_rect.right - panel_width
    x = _clamp(desired_x, screen.left, screen.right - panel_width)

    below_y = anchor_rect.bottom
    if below_y + panel_height <= screen.bottom:
        y = below_y
    else:
        y = anchor_rect.top - panel_height

    y = _clamp(y, screen.top, screen.bottom - panel_height)
    return (x, y)


def _contains(screen: ScreenRect, point: tuple[int, int]) -> bool:
    x, y = point
    return screen.left <= x < screen.right and screen.top <= y < screen.bottom


def _distance_to_rect_squared(screen: ScreenRect, point: tuple[int, int]) -> int:
    x, y = point
    nearest_x = _clamp(x, screen.left, screen.right)
    nearest_y = _clamp(y, screen.top, screen.bottom)
    return (x - nearest_x) ** 2 + (y - nearest_y) ** 2


def _clamp(value: int, minimum: int, maximum: int) -> int:
    if minimum > maximum:
        return minimum
    return max(minimum, min(value, maximum))
