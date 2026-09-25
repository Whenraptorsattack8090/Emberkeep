#!/usr/bin/env python3
"""
EMBERKEEP - a 2D pixel-art dungeon adventure that runs in its own window.

Setup (once):   pip install pygame
Run:            python emberkeep.py

Controls
  WASD / arrows   move              SPACE / J / click   attack (click aims)
  SHIFT / K       dash              P / ESC             pause
  R               restart           C                   change class
  H               back to the camp (from the pause or game over screen)
  M               sound on/off      F11                 fullscreen
  [ ]  music volume      , .  sound volume      (or drag the sliders in the start menu)

The dungeon is drawn with big chunky pixels; characters and effects use finer ones.
"""
import array
import json
import math
import random
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace as NS

import pygame

# ----------------------------------------------------------------------------
# Layout: the game world is 320x192 "units". The canvas is 2x that (640x384).
# Background pixels are 4 canvas px, character pixels are 2 canvas px.
# ----------------------------------------------------------------------------
W, H = 320, 192
SC = 2
CW, CH = W * SC, H * SC
T = 16
COLS, ROWS = 20, 12
CT = 8  # background pixels per tile

FLOOR_TINT = (58, 53, 96)
OUTLINE = (13, 10, 24)
SHADOW = (11, 8, 20)

SAVE_PATH = Path(__file__).resolve().with_name("emberkeep_save.json")
LEGACY_SAVE_PATH = Path(__file__).resolve().with_name("duskblade_save.json")  # from before the rename


def C(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rnd(v):
    """Round half up (like JavaScript's Math.round)."""
    return int(math.floor(v + 0.5))


def clamp(v, a, b):
    return max(a, min(b, v))


def ang_diff(a, b):
    d = a - b
    while d > math.pi:
        d -= 2 * math.pi
    while d < -math.pi:
        d += 2 * math.pi
    return d


def lerp_color(a, b, t):
    t = clamp(t, 0.0, 1.0)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


# ----------------------------------------------------------------------------
# Tiny built-in 5x7 pixel font (no font files needed)
# ----------------------------------------------------------------------------
_FONT_SRC = {
    "A": ".###./#...#/#...#/#####/#...#/#...#/#...#",
    "B": "####./#...#/#...#/####./#...#/#...#/####.",
    "C": ".###./#...#/#..../#..../#..../#...#/.###.",
    "D": "####./#...#/#...#/#...#/#...#/#...#/####.",
    "E": "#####/#..../#..../####./#..../#..../#####",
    "F": "#####/#..../#..../####./#..../#..../#....",
    "G": ".###./#...#/#..../#.###/#...#/#...#/.###.",
    "H": "#...#/#...#/#...#/#####/#...#/#...#/#...#",
    "I": ".###./..#../..#../..#../..#../..#../.###.",
    "J": "..###/...#./...#./...#./...#./#..#./.##..",
    "K": "#...#/#..#./#.#../##.../#.#../#..#./#...#",
    "L": "#..../#..../#..../#..../#..../#..../#####",
    "M": "#...#/##.##/#.#.#/#.#.#/#...#/#...#/#...#",
    "N": "#...#/##..#/#.#.#/#..##/#...#/#...#/#...#",
    "O": ".###./#...#/#...#/#...#/#...#/#...#/.###.",
    "P": "####./#...#/#...#/####./#..../#..../#....",
    "Q": ".###./#...#/#...#/#...#/#.#.#/#..#./.##.#",
    "R": "####./#...#/#...#/####./#.#../#..#./#...#",
    "S": ".####/#..../#..../.###./....#/....#/####.",
    "T": "#####/..#../..#../..#../..#../..#../..#..",
    "U": "#...#/#...#/#...#/#...#/#...#/#...#/.###.",
    "V": "#...#/#...#/#...#/#...#/#...#/.#.#./..#..",
    "W": "#...#/#...#/#...#/#.#.#/#.#.#/##.##/#...#",
    "X": "#...#/#...#/.#.#./..#../.#.#./#...#/#...#",
    "Y": "#...#/#...#/.#.#./..#../..#../..#../..#..",
    "Z": "#####/....#/...#./..#../.#.../#..../#####",
    "0": ".###./#...#/#..##/#.#.#/##..#/#...#/.###.",
    "1": "..#../.##../..#../..#../..#../..#../.###.",
    "2": ".###./#...#/....#/...#./..#../.#.../#####",
    "3": ".###./#...#/....#/..##./....#/#...#/.###.",
    "4": "...#./..##./.#.#./#..#./#####/...#./...#.",
    "5": "#####/#..../####./....#/....#/#...#/.###.",
    "6": "..##./.#.../#..../####./#...#/#...#/.###.",
    "7": "#####/....#/...#./..#../.#.../.#.../.#...",
    "8": ".###./#...#/#...#/.###./#...#/#...#/.###.",
    "9": ".###./#...#/#...#/.####/....#/...#./.##..",
    ":": "...../..#../..#../...../..#../..#../.....",
    "/": "....#/....#/...#./..#../.#.../#..../#....",
    ",": "...../...../...../...../..##./..#../.#...",
    ".": "...../...../...../...../...../.##../.##..",
    "?": ".###./#...#/....#/...#./..#../...../..#..",
    "+": "...../..#../..#../#####/..#../..#../.....",
    "-": "...../...../...../#####/...../...../.....",
    "!": "..#../..#../..#../..#../..#../...../..#..",
    " ": "...../...../...../...../...../...../.....",
}
FONT = {k: v.split("/") for k, v in _FONT_SRC.items()}
_glyph_cache = {}
_alpha_cache = {}


def glyph(ch, scale, color):
    key = (ch, scale, color)
    g = _glyph_cache.get(key)
    if g is None:
        rows = FONT.get(ch) or FONT["?"]
        g = pygame.Surface((5 * scale, 7 * scale), pygame.SRCALPHA)
        for y, row in enumerate(rows):
            for x, c in enumerate(row):
                if c == "#":
                    g.fill(color, (x * scale, y * scale, scale, scale))
        _glyph_cache[key] = g
    return g


def text_width(s, scale):
    return max(0, len(s) * 6 * scale - scale)


def draw_text(surf, s, x, y, color, align="left", scale=2):
    """Draw pixel text. x, y are world units; scale = canvas px per font pixel."""
    s = s.upper()
    px = int(x * SC)
    py = int(y * SC)
    w = text_width(s, scale)
    if align == "center":
        px -= w // 2
    elif align == "right":
        px -= w
    for shadow in (True, False):
        col = SHADOW if shadow else color
        off = scale if shadow else 0
        cx = px + off
        for ch in s:
            surf.blit(glyph(ch, scale, col), (cx, py + off))
            cx += 6 * scale


def alpha_surf(w, h, color, alpha):
    key = (w, h, color, alpha)
    s = _alpha_cache.get(key)
    if s is None:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        s.fill(color + (int(alpha * 255),))
        _alpha_cache[key] = s
    return s


def frect(surf, x, y, w, h, color):
    """Fill a rectangle given in world units."""
    surf.fill(color, (int(x * SC), int(y * SC), int(w * SC), int(h * SC)))


# ----------------------------------------------------------------------------
# Sprites: hand-drawn pixel art from text, with a 1-pixel outline
# ----------------------------------------------------------------------------
class Sprite:
    def __init__(self, rows, pal):
        self.h = len(rows)
        self.w = len(rows[0])
        w, h = self.w, self.h
        body = pygame.Surface((w, h), pygame.SRCALPHA)
        for y, r in enumerate(rows):
            for x, ch in enumerate(r):
                if ch != "." and ch in pal:
                    body.set_at((x, y), C(pal[ch]) + (255,))

        def silhouette(color):
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            for yy in range(h):
                for xx in range(w):
                    if body.get_at((xx, yy))[3]:
                        s.set_at((xx, yy), color + (255,))
            return s

        def build(fill):
            o = pygame.Surface((w + 2, h + 2), pygame.SRCALPHA)
            dark = silhouette(OUTLINE)
            for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2)):
                o.blit(dark, (dx, dy))
            o.blit(fill, (1, 1))
            return pygame.transform.scale(o, ((w + 2) * SC, (h + 2) * SC))

        self.img = build(body)
        self.white = build(silhouette((255, 255, 255)))
        self.imgf = pygame.transform.flip(self.img, True, False)
        self.whitef = pygame.transform.flip(self.white, True, False)
        self.big = pygame.transform.scale(self.img, (self.img.get_width() * 2, self.img.get_height() * 2))

    def convert(self):
        self.img = self.img.convert_alpha()
        self.white = self.white.convert_alpha()
        self.imgf = self.imgf.convert_alpha()
        self.whitef = self.whitef.convert_alpha()
        self.big = self.big.convert_alpha()


def spr_big(surf, s, cx, by, alpha=1.0):
    """Menu-size sprite (double the pixel size), feet at by (world units)."""
    x = int(cx * SC - s.big.get_width() / 2)
    y = int(by * SC - (s.h + 1) * SC * 2)
    s.big.set_alpha(int(clamp(alpha, 0, 1) * 255))
    surf.blit(s.big, (x, y))
    s.big.set_alpha(255)


def spr(surf, s, cx, by, flip=False, white=False, alpha=None):
    """Draw a sprite centred on cx with its feet at by (world units)."""
    if white:
        img = s.whitef if flip else s.white
    else:
        img = s.imgf if flip else s.img
    x = (rnd(cx - s.w / 2) - 1) * SC
    y = (rnd(by - s.h) - 1) * SC
    if alpha is not None:
        img.set_alpha(int(clamp(alpha, 0, 1) * 255))
        surf.blit(img, (x, y))
        img.set_alpha(255)
    else:
        surf.blit(img, (x, y))


# ----------------------------------------------------------------------------
# Sprite art: one string per pixel row. '.' is transparent; letters map to the palette.
# ----------------------------------------------------------------------------
SPRITE_DATA = {
    "rogue": (
        [
            "....1111111....",
            "...112222211...",
            "..11222222211..",
            "..12222222221..",
            "..12ddddddd21..",
            "..1ddedddedd1..",
            "..1ddddddddd1..",
            "..122ddddd221..",
            ".1222222222221.",
            ".1222322232221.",
            ".1222322232221.",
            ".1222322232221.",
            ".1bbbbbwbbbbb1.",
            ".1222322232221.",
            "..12222222221..",
            "...kkk...kkk...",
            "...kkk...kkk...",
            "..nnnn...nnnn..",
        ],
        {'1': '#1f3a6e', '2': '#3f7fd9', '3': '#7fb5ff', 'd': '#141020', 'e': '#9fe8ff', 'b': '#e0a83c', 'w': '#fff3c4', 'n': '#6b4226', 'k': '#2a2440'},
    ),
    "knight": (
        [
            "......ppp......",
            ".....ppppp.....",
            "...hhhhhhhhh...",
            "..hhHHhhhHHhh..",
            "..hhhhhhhhhhh..",
            "..hdddddddddh..",
            "..hhhhhhhhhhh..",
            "..hhhhhdhhhhh..",
            "...hhhhhhhhh...",
            ".hHhhhhhhhhhHh.",
            ".hhhhttttthhhh.",
            ".hhhhttttthhhh.",
            ".hsssbbbbbsssh.",
            "..hhhttttthhh..",
            "..hhhttttthhh..",
            "...hhh...hhh...",
            "...hhh...hhh...",
            "..nnnn...nnnn..",
        ],
        {'h': '#9aa5b8', 'H': '#d0d8e6', 's': '#5a6478', 'd': '#141020', 'p': '#d04a4a', 't': '#3f7fd9', 'b': '#e0a83c', 'n': '#3a3450'},
    ),
    "mage": (
        [
            ".......q.......",
            "......ppp......",
            ".....ppppp.....",
            "....pPpppPp....",
            "...ppPpppPpp...",
            "...pbbbbbbbp...",
            ".qqqqqqqqqqqqq.",
            "....sssssss....",
            "....sksssks....",
            "...wwwwwwwww...",
            ".ppppwwwwwpppp.",
            ".ppPpwwwwwpPpp.",
            ".pbbbbbbbbbbbp.",
            ".ppppPpppPpppp.",
            "..ppppppppppp..",
            "..ppppqqqpppp..",
            "..qq.qqqqq.qq..",
        ],
        {'p': '#5b3fa0', 'P': '#8a6be0', 'q': '#2d1f5c', 's': '#f2c9a0', 'k': '#141020', 'w': '#f4f0ff', 'y': '#ffd34d', 'b': '#e0a83c', 'n': '#3a3450'},
    ),
    "slime": (
        [
            "......aaaaaa......",
            "....aaaaaaaaaa....",
            "...aaAAaaaaAAaa...",
            "..aaAAaaaaaaAAaa..",
            ".aaaAaaaaaaaaAaaa.",
            ".aaaaaaaaaaaaaaaa.",
            "aaakkaaaaaaaakkaaa",
            "aaakkaaaaaaaakkaaa",
            "aaaaaaaaaaaaaaaaaa",
            "aaaaaaakkkkaaaaaaa",
            "aDaaaaaaaaaaaaaaDa",
            "aDaaaaaaaaaaaaaaDa",
            ".DDDDDDDDDDDDDDDD.",
            "..DDDDDDDDDDDDDD..",
        ],
        {'a': '#4fd08a', 'A': '#a6f2c4', 'D': '#2a8f5c', 'k': '#10231a', 'w': '#ffffff'},
    ),
    "bat0": (
        [
            "D......D..D......D",
            "DD....DDDDDD....DD",
            "DDD..DDdDDdDD..DDD",
            "DDDDDDrDDDDrDDDDDD",
            ".DDDDDDDDDDDDDDDD.",
            "..DDDDDDwwDDDDDD..",
            "....DDD....DDD....",
        ],
        {'D': '#6a45a0', 'd': '#8b5fd0', 'r': '#ff5a7a', 'w': '#ffffff'},
    ),
    "bat1": (
        [
            "..................",
            "......D....D......",
            "D....DDdDDdDD....D",
            "DDDDDDrDDDDrDDDDDD",
            "DDDDDDDDDDDDDDDDDD",
            ".DD.DDDDwwDDDD.DD.",
            "D....DDD..DDD....D",
        ],
        {'D': '#6a45a0', 'd': '#8b5fd0', 'r': '#ff5a7a', 'w': '#ffffff'},
    ),
    "skel": (
        [
            ".......wwwwwww.......",
            "......wwwwwwwww......",
            ".....wwwwwwwwwww.....",
            ".....wkkwwwwwkkw.....",
            ".....wkewwwwwekw.....",
            ".....wwwwwkwwwww.....",
            "......wwwwwwwww......",
            ".......wkwkwkw.......",
            ".......wwwwwww.......",
            "..........w..........",
            ".....wwwwwwwwwww.....",
            ".....w.wwwwwww.w.....",
            ".....w.wkkwkkw.w.....",
            ".....w.wwwwwww.w.....",
            ".....w.wkkwkkw.w.....",
            ".....w..wwwww..w.....",
            "......wwwwwwwww......",
            "........w...w........",
            "........w...w........",
            ".......www.www.......",
        ],
        {'w': '#f2ecd8', 'g': '#b9b29a', 'k': '#1a1626', 'e': '#ff5a4d', 'S': '#c9b48a', 'T': '#e8f0ff', 'F': '#ff5a7a'},
    ),
    "heart": (
        [
            ".rr.rr.",
            "rrrrrrr",
            "rrrrrrr",
            ".rrrrr.",
            "..rrr..",
            "...r...",
        ],
        {'r': '#ff4d6d'},
    ),
    "heart_empty": (
        [
            ".rr.rr.",
            "rrrrrrr",
            "rrrrrrr",
            ".rrrrr.",
            "..rrr..",
            "...r...",
        ],
        {'r': '#3a2f4d'},
    ),
    "slime_crouch": (
        [
            "......aaaaaaaa......",
            "....aaaaaaaaaaaa....",
            "..aaAAaaaaaaaaAAaa..",
            ".aaaAAaaaaaaaaAAaaa.",
            "aaakkaaaaaaaaaakkaaa",
            "aaakkaaaaaaaaaakkaaa",
            "aaaaaaaaaaaaaaaaaaaa",
            "aaaaaaaakkkkaaaaaaaa",
            "aDaaaaaaaaaaaaaaaaDa",
            ".DDDDDDDDDDDDDDDDDD.",
            "..DDDDDDDDDDDDDDDD..",
        ],
        {'a': '#4fd08a', 'A': '#a6f2c4', 'D': '#2a8f5c', 'k': '#10231a', 'w': '#ffffff'},
    ),
    "slime_stretch": (
        [
            ".....aaaaaa.....",
            "....aaaaaaaa....",
            "...aaAAaaAAaa...",
            "...aAAaaaaAAa...",
            "..aaaAaaaaAaaa..",
            "..aaaaaaaaaaaa..",
            "..akkaaaaaakka..",
            "..akkaaaaaakka..",
            "..aaaaaaaaaaaa..",
            "..aaaaakkaaaaa..",
            "..aaaaakkaaaaa..",
            "..aaaaaaaaaaaa..",
            "..aDaaaaaaaaDa..",
            "...DDaaaaaaDD...",
            "...DDDDDDDDDD...",
            "....DDDDDDDD....",
            ".....DDDDDD.....",
        ],
        {'a': '#4fd08a', 'A': '#a6f2c4', 'D': '#2a8f5c', 'k': '#10231a', 'w': '#ffffff'},
    ),
    "skel_a": (
        [
            ".......wwwwwww.......",
            "......wwwwwwwww......",
            ".....wwwwwwwwwww.....",
            ".....wkkwwwwwkkw.....",
            ".....wkewwwwwekw.....",
            ".....wwwwwkwwwww.....",
            "......wwwwwwwww......",
            ".......wkwkwkw.......",
            ".......wwwwwww.......",
            "..........w..........",
            ".....wwwwwwwwwww.....",
            ".....w.wwwwwww.w.....",
            ".....w.wkkwkkw.w.....",
            ".....w.wwwwwww.w.....",
            ".....w.wkkwkkw.w.....",
            "....w...wwwww........",
            "......wwwwwwwww......",
            "........w...w........",
            ".......ww...w........",
            "...........www.......",
        ],
        {'w': '#f2ecd8', 'g': '#b9b29a', 'k': '#1a1626', 'e': '#ff5a4d', 'S': '#c9b48a', 'T': '#e8f0ff', 'F': '#ff5a7a'},
    ),
    "skel_b": (
        [
            ".......wwwwwww.......",
            "......wwwwwwwww......",
            ".....wwwwwwwwwww.....",
            ".....wkkwwwwwkkw.....",
            ".....wkewwwwwekw.....",
            ".....wwwwwkwwwww.....",
            "......wwwwwwwww......",
            ".......wkwkwkw.......",
            ".......wwwwwww.......",
            "..........w..........",
            ".....wwwwwwwwwww.....",
            ".....w.wwwwwww.w.....",
            ".....w.wkkwkkw.w.....",
            ".....w.wwwwwww.w.....",
            ".....w.wkkwkkw.w.....",
            "........wwwww...w....",
            "......wwwwwwwww......",
            "........w...w........",
            "........w...ww.......",
            ".......www...........",
        ],
        {'w': '#f2ecd8', 'g': '#b9b29a', 'k': '#1a1626', 'e': '#ff5a4d', 'S': '#c9b48a', 'T': '#e8f0ff', 'F': '#ff5a7a'},
    ),
    "skel_windup1": (
        [
            ".......wwwwwww.......",
            "......wwwwwwwww......",
            ".....wwwwwwwwwww.....",
            ".....wkkwwwwwkkw.....",
            ".....wkewwwwwekw.....",
            ".....wwwwwkwwwww.....",
            "......wwwwwwwww......",
            ".......wkwkwkw...FSST",
            ".......wwwwwww...w...",
            "..........w......w...",
            ".....wwwwwwwwwwwww...",
            ".....w.wwwwwww.......",
            ".....w.wkkwkkw.......",
            ".....w.wwwwwww.......",
            ".....w.wkkwkkw.......",
            ".....w..wwwww........",
            "......wwwwwwwww......",
            "........w...w........",
            "........w...w........",
            ".......www.www.......",
        ],
        {'w': '#f2ecd8', 'g': '#b9b29a', 'k': '#1a1626', 'e': '#ff5a4d', 'S': '#c9b48a', 'T': '#e8f0ff', 'F': '#ff5a7a'},
    ),
    "skel_windup2": (
        [
            ".......wwwwwww.......",
            "......wwwwwwwww......",
            ".....wwwwwwwwwww.....",
            ".....wkkwwwwwkkw.....",
            ".....wkewwwwwekw.....",
            ".....wwwwwkwwwww.FSST",
            "......wwwwwwwww..w...",
            ".......wkwkwkw...w...",
            ".......wwwwwww...w...",
            "..........w......w...",
            ".....wwwwwwwwwwwww...",
            ".....w.wwwwwww.......",
            ".....w.wkkwkkw.......",
            ".....w.wwwwwww.......",
            ".....w.wkkwkkw.......",
            ".....w..wwwww........",
            "......wwwwwwwww......",
            "........w...w........",
            "........w...w........",
            ".......www.www.......",
        ],
        {'w': '#f2ecd8', 'g': '#b9b29a', 'k': '#1a1626', 'e': '#ff5a4d', 'S': '#c9b48a', 'T': '#e8f0ff', 'F': '#ff5a7a'},
    ),
    "skel_throw": (
        [
            ".......wwwwwww.......",
            "......wwwwwwwww......",
            ".....wwwwwwwwwww.....",
            ".....wkkwwwwwkkw.....",
            ".....wkewwwwwekw.....",
            ".....wwwwwkwwwww.....",
            "......wwwwwwwww......",
            ".......wkwkwkw.......",
            ".......wwwwwww.......",
            "..........w.......www",
            ".....wwwwwwwwwwwww...",
            ".....w.wwwwwww.......",
            ".....w.wkkwkkw.......",
            ".....w.wwwwwww.......",
            ".....w.wkkwkkw.......",
            ".....w..wwwww........",
            "......wwwwwwwww......",
            "........w...w........",
            "........w...w........",
            ".......www.www.......",
        ],
        {'w': '#f2ecd8', 'g': '#b9b29a', 'k': '#1a1626', 'e': '#ff5a4d', 'S': '#c9b48a', 'T': '#e8f0ff', 'F': '#ff5a7a'},
    ),
    "skel_follow": (
        [
            ".......wwwwwww.......",
            "......wwwwwwwww......",
            ".....wwwwwwwwwww.....",
            ".....wkkwwwwwkkw.....",
            ".....wkewwwwwekw.....",
            ".....wwwwwkwwwww.....",
            "......wwwwwwwww......",
            ".......wkwkwkw.......",
            ".......wwwwwww.......",
            "..........w..........",
            ".....wwwwwwwwwww.....",
            ".....w.wwwwwww..w....",
            ".....w.wkkwkkw...w...",
            ".....w.wwwwwww....w..",
            ".....w.wkkwkkw....w..",
            ".....w..wwwww........",
            "......wwwwwwwww......",
            "........w...w........",
            "........w...w........",
            ".......www.www.......",
        ],
        {'w': '#f2ecd8', 'g': '#b9b29a', 'k': '#1a1626', 'e': '#ff5a4d', 'S': '#c9b48a', 'T': '#e8f0ff', 'F': '#ff5a7a'},
    ),
}


# ----------------------------------------------------------------------------
# Player animation frames (idle, breathe, walk x2, dash, hurt, attack wind-up, attack swing).
# Every class faces right; the sprite is flipped when the player faces left.
# ----------------------------------------------------------------------------
PLAYER_ART = {
    "knight": {
        "pal": {'h': '#9aa5b8', 'H': '#d0d8e6', 's': '#5a6478', 'd': '#141020', 'p': '#d04a4a', 't': '#3f7fd9', 'b': '#e0a83c', 'n': '#3a3450', 'L': '#e8f0ff', 'M': '#aab6cc', 'Y': '#e0a83c', 'G': '#6b4226', 'O': '#8fc4ff', 'W': '#ffffff'},
        "frames": {
            "idle0": [
                "..............ppp..............",
                ".............ppppp.............",
                "...........hhhhhhhhh...........",
                "..........hhHHhhhHHhh..........",
                "..........hhhhhhhhhhh..........",
                "..........hdddddddddh..........",
                "..........hhhhhhhhhhh..........",
                "..........hhhhhdhhhhh..........",
                "...........hhhhhhhhh...G.......",
                ".........hHhhhhhhhhhHhYYY......",
                ".........hhhhttttthhhh.L.......",
                ".........hhhhttttthhhh.L.......",
                ".........hsssbbbbbsssh.L.......",
                "..........hhhttttthhh..L.......",
                "..........hhhttttthhh..L.......",
                "...........hhh...hhh...L.......",
                "...........hhh...hhh...M.......",
                "..........nnnn...nnnn..........",
            ],
            "idle1": [
                "..............ppp..............",
                ".............ppppp.............",
                "...........hhhhhhhhh...........",
                "..........hhHHhhhHHhh..........",
                "..........hhhhhhhhhhh..........",
                "..........hdddddddddh..........",
                "..........hhhhhhhhhhh..........",
                "..........hhhhhdhhhhh..........",
                "...........hhhhhhhhh...G.......",
                ".........hHhhhhhhhhhHhYYY......",
                ".........hhhhttttthhhh.L.......",
                ".........hhhhttttthhhh.L.......",
                ".........hhhhttttthhhh.L.......",
                ".........hsssbbbbbsssh.L.......",
                "..........hhhttttthhh..L.......",
                "..........hhhttttthhh..L.......",
                "...........hhh...hhh...L.......",
                "...........hhh...hhh...M.......",
                "..........nnnn...nnnn..........",
            ],
            "walk_a": [
                "..............ppp..............",
                ".............ppppp.............",
                "...........hhhhhhhhh...........",
                "..........hhHHhhhHHhh..........",
                "..........hhhhhhhhhhh..........",
                "..........hdddddddddh..........",
                "..........hhhhhhhhhhh..........",
                "..........hhhhhdhhhhh..........",
                "...........hhhhhhhhh...G.......",
                ".........hHhhhhhhhhhHhYYY......",
                ".........hhhhttttthhhh.L.......",
                ".........hhhhttttthhhh.L.......",
                ".........hsssbbbbbsssh.L.......",
                "..........hhhttttthhh..L.......",
                "..........hhhttttthhh..L.......",
                "...........hhh...hhh...L.......",
                "..........nnnn...hhh...M.......",
                ".................nnnn..........",
            ],
            "walk_b": [
                "..............ppp..............",
                ".............ppppp.............",
                "...........hhhhhhhhh...........",
                "..........hhHHhhhHHhh..........",
                "..........hhhhhhhhhhh..........",
                "..........hdddddddddh..........",
                "..........hhhhhhhhhhh..........",
                "..........hhhhhdhhhhh..........",
                "...........hhhhhhhhh...G.......",
                ".........hHhhhhhhhhhHhYYY......",
                ".........hhhhttttthhhh.L.......",
                ".........hhhhttttthhhh.L.......",
                ".........hsssbbbbbsssh.L.......",
                "..........hhhttttthhh..L.......",
                "..........hhhttttthhh..L.......",
                "...........hhh...hhh...L.......",
                "...........hhh...nnnn..M.......",
                "..........nnnn.................",
            ],
            "dash": [
                ".................ppp...........",
                "................ppppp..........",
                "..............hhhhhhhhh........",
                "............hhHHhhhHHhh........",
                "............hhhhhhhhhhh........",
                "............hdddddddddh........",
                "............hhhhhhhhhhh........",
                "............hhhhhdhhhhh........",
                ".............hhhhhhhhh...G.....",
                "..........hHhhhhhhhhhHhYYY.....",
                "..........hhhhttttthhhh.L......",
                "..........hhhhttttthhhh.L......",
                "..........hsssbbbbbsssh.L......",
                "...........hhhttttthhh..L......",
                "...........hhhttttthhh..L......",
                "...........hhh...hhh...L.......",
                "..........nnnn...hhh...M.......",
                ".................nnnn..........",
            ],
            "hurt": [
                "............ppp................",
                "...........ppppp...............",
                ".........hhhhhhhhh.............",
                "........hhHHhhhHHhh............",
                "........hhhhhhhhhhh............",
                ".........hdddddddddh...........",
                ".........hhhhhhhhhhh...........",
                ".........hhhhhdhhhhh...........",
                "..........hhhhhhhhh...G........",
                "........hHhhhhhhhhhHhYYY.......",
                "........hhhhttttthhhh.L........",
                "........hhhhttttthhhh.L........",
                "........hsssbbbbbsssh.L........",
                "..........hhhttttthhh..L.......",
                "..........hhhttttthhh..L.......",
                "...........hhh...hhh...L.......",
                "...........hhh...hhh...M.......",
                "..........nnnn...nnnn..........",
            ],
            "attack1": [
                "..............ppp.....LM.......",
                ".............ppppp....LM.......",
                "...........hhhhhhhhh..LM.......",
                "..........hhHHhhhHHhh.LM.......",
                "..........hhhhhhhhhhh.LM.......",
                "..........hdddddddddh.LM.......",
                "..........hhhhhhhhhhh.LM.......",
                "..........hhhhhdhhhhhYYY.......",
                "...........hhhhhhhhh..h........",
                ".........hHhhhhhhhhhHhh........",
                ".........hhhhttttthhhh.........",
                ".........hhhhttttthhhh.........",
                ".........hsssbbbbbsssh.........",
                "..........hhhttttthhh..........",
                "..........hhhttttthhh..........",
                "...........hhh...hhh...........",
                "...........hhh...hhh...........",
                "..........nnnn...nnnn..........",
            ],
            "attack2": [
                "...............ppp.............",
                "..............ppppp............",
                "............hhhhhhhhh..........",
                "...........hhHHhhhHHhh.........",
                "...........hhhhhhhhhhh.........",
                "...........hdddddddddh.........",
                "...........hhhhhhhhhhh.........",
                "...........hhhhhdhhhhh.........",
                "............hhhhhhhhh..........",
                ".........hHhhhhhhhhhHh..Y......",
                ".........hhhhttttthhhhhHYLLLLLL",
                ".........hhhhttttthhhh..YMMMMMM",
                ".........hsssbbbbbsssh.........",
                "..........hhhttttthhh..........",
                "..........hhhttttthhh..........",
                "...........hhh...hhh...........",
                "...........hhh...hhh...........",
                "..........nnnn...nnnn..........",
            ],
        },
    },
    "rogue": {
        "pal": {'1': '#1f3a6e', '2': '#3f7fd9', '3': '#7fb5ff', 'd': '#141020', 'e': '#9fe8ff', 'b': '#e0a83c', 'w': '#fff3c4', 'n': '#6b4226', 'k': '#2a2440', 'L': '#e8f0ff', 'M': '#aab6cc', 'Y': '#e0a83c', 'G': '#6b4226', 'O': '#8fc4ff', 'W': '#ffffff'},
        "frames": {
            "idle0": [
                "............1111111............",
                "...........112222211...........",
                "..........11222222211..........",
                "..........12222222221..........",
                "..........12ddddddd21..........",
                "..........1ddedddedd1..........",
                "..........1ddddddddd1..........",
                "..........122ddddd221..........",
                ".........1222222222221.........",
                ".........1222322232221.G.......",
                ".........1222322232221YYY......",
                ".........1222322232221.L.......",
                ".........1bbbbbwbbbbb1.L.......",
                ".........1222322232221.L.......",
                "..........12222222221..M.......",
                "...........kkk...kkk...........",
                "...........kkk...kkk...........",
                "..........nnnn...nnnn..........",
            ],
            "idle1": [
                "............1111111............",
                "...........112222211...........",
                "..........11222222211..........",
                "..........12222222221..........",
                "..........12ddddddd21..........",
                "..........1ddedddedd1..........",
                "..........1ddddddddd1..........",
                "..........122ddddd221..........",
                ".........1222222222221.........",
                ".........1222322232221.G.......",
                ".........1222322232221YYY......",
                ".........1222322232221YYY......",
                ".........1222322232221.L.......",
                ".........1bbbbbwbbbbb1.L.......",
                ".........1222322232221.L.......",
                "..........12222222221..M.......",
                "...........kkk...kkk...........",
                "...........kkk...kkk...........",
                "..........nnnn...nnnn..........",
            ],
            "walk_a": [
                "............1111111............",
                "...........112222211...........",
                "..........11222222211..........",
                "..........12222222221..........",
                "..........12ddddddd21..........",
                "..........1ddedddedd1..........",
                "..........1ddddddddd1..........",
                "..........122ddddd221..........",
                ".........1222222222221.........",
                ".........1222322232221.G.......",
                ".........1222322232221YYY......",
                ".........1222322232221.L.......",
                ".........1bbbbbwbbbbb1.L.......",
                ".........1222322232221.L.......",
                "..........12222222221..M.......",
                "...........kkk...kkk...........",
                "..........nnnn...kkk...........",
                ".................nnnn..........",
            ],
            "walk_b": [
                "............1111111............",
                "...........112222211...........",
                "..........11222222211..........",
                "..........12222222221..........",
                "..........12ddddddd21..........",
                "..........1ddedddedd1..........",
                "..........1ddddddddd1..........",
                "..........122ddddd221..........",
                ".........1222222222221.........",
                ".........1222322232221.G.......",
                ".........1222322232221YYY......",
                ".........1222322232221.L.......",
                ".........1bbbbbwbbbbb1.L.......",
                ".........1222322232221.L.......",
                "..........12222222221..M.......",
                "...........kkk...kkk...........",
                "...........kkk...nnnn..........",
                "..........nnnn.................",
            ],
            "dash": [
                "...............1111111.........",
                "..............112222211........",
                ".............11222222211.......",
                "............12222222221........",
                "............12ddddddd21........",
                "............1ddedddedd1........",
                "............1ddddddddd1........",
                "............122ddddd221........",
                "...........1222222222221.......",
                "..........1222322232221.G......",
                "..........1222322232221YYY.....",
                "..........1222322232221.L......",
                "..........1bbbbbwbbbbb1.L......",
                "..........1222322232221.L......",
                "...........12222222221..M......",
                "...........kkk...kkk...........",
                "..........nnnn...kkk...........",
                ".................nnnn..........",
            ],
            "hurt": [
                "..........1111111..............",
                ".........112222211.............",
                "........11222222211............",
                "........12222222221............",
                "........12ddddddd21............",
                ".........1ddedddedd1...........",
                ".........1ddddddddd1...........",
                ".........122ddddd221...........",
                "........1222222222221..........",
                "........1222322232221.G........",
                "........1222322232221YYY.......",
                "........1222322232221.L........",
                "........1bbbbbwbbbbb1.L........",
                ".........1222322232221.L.......",
                "..........12222222221..M.......",
                "...........kkk...kkk...........",
                "...........kkk...kkk...........",
                "..........nnnn...nnnn..........",
            ],
            "attack1": [
                "............1111111............",
                "...........112222211...M.......",
                "..........11222222211..L.......",
                "..........12222222221..L.......",
                "..........12ddddddd21..L.......",
                "..........1ddedddedd1..L.......",
                "..........1ddddddddd1.YYY......",
                "..........122ddddd221..w.......",
                ".........1222222222221.2.......",
                ".........12223222322212........",
                ".........1222322232221.........",
                ".........1222322232221.........",
                ".........1bbbbbwbbbbb1.........",
                ".........1222322232221.........",
                "..........12222222221..........",
                "...........kkk...kkk...........",
                "...........kkk...kkk...........",
                "..........nnnn...nnnn..........",
            ],
            "attack2": [
                ".............1111111...........",
                "............112222211..........",
                "...........11222222211.........",
                "...........12222222221.........",
                "...........12ddddddd21.........",
                "...........1ddedddedd1.........",
                "...........1ddddddddd1.........",
                "...........122ddddd221.........",
                "..........1222222222221........",
                ".........1222322232221...Y.....",
                ".........122232223222122wYLLLLM",
                ".........1222322232221...Y.....",
                ".........1bbbbbwbbbbb1.........",
                ".........1222322232221.........",
                "..........12222222221..........",
                "...........kkk...kkk...........",
                "...........kkk...kkk...........",
                "..........nnnn...nnnn..........",
            ],
        },
    },
    "mage": {
        "pal": {'p': '#5b3fa0', 'P': '#8a6be0', 'q': '#2d1f5c', 's': '#f2c9a0', 'k': '#141020', 'w': '#f4f0ff', 'y': '#ffd34d', 'b': '#e0a83c', 'n': '#3a3450', 'L': '#e8f0ff', 'M': '#aab6cc', 'Y': '#e0a83c', 'G': '#6b4226', 'O': '#8fc4ff', 'W': '#ffffff'},
        "frames": {
            "idle0": [
                "......................O........",
                ".....................OWO.......",
                "......................O........",
                "...............q...............",
                "..............ppp..............",
                ".............ppppp.............",
                "............pPpppPp...G........",
                "...........ppPpppPpp..G........",
                "...........pbbbbbbbp..G........",
                ".........qqqqqqqqqqqqqG........",
                "............sssssss...G........",
                "............sksssks...G........",
                "...........wwwwwwwww..G........",
                ".........ppppwwwwwppppG........",
                ".........ppPpwwwwwpPppG........",
                ".........pbbbbbbbbbbbpG........",
                ".........ppppPpppPppppG........",
                "..........ppppppppppp.G........",
                "..........ppppqqqpppp.G........",
                "..........qq.qqqqq.qq.G........",
            ],
            "idle1": [
                "......................O........",
                ".....................OWO.......",
                "......................O........",
                "...............q...............",
                "..............ppp..............",
                ".............ppppp.............",
                "............pPpppPp...G........",
                "...........ppPpppPpp..G........",
                "...........pbbbbbbbp..G........",
                ".........qqqqqqqqqqqqqG........",
                "............sssssss...G........",
                "............sksssks...G........",
                "...........wwwwwwwww..G........",
                ".........ppppwwwwwppppG........",
                ".........ppPpwwwwwpPppG........",
                ".........ppPpwwwwwpPppG........",
                ".........pbbbbbbbbbbbpG........",
                ".........ppppPpppPppppG........",
                "..........ppppppppppp.G........",
                "..........ppppqqqpppp.G........",
                "..........qq.qqqqq.qq.G........",
            ],
            "walk_a": [
                "......................O........",
                ".....................OWO.......",
                "......................O........",
                "...............q...............",
                "..............ppp..............",
                ".............ppppp.............",
                "............pPpppPp...G........",
                "...........ppPpppPpp..G........",
                "...........pbbbbbbbp..G........",
                ".........qqqqqqqqqqqqqG........",
                "............sssssss...G........",
                "............sksssks...G........",
                "...........wwwwwwwww..G........",
                ".........ppppwwwwwppppG........",
                ".........ppPpwwwwwpPppG........",
                ".........pbbbbbbbbbbbpG........",
                ".........ppppPpppPppppG........",
                "..........ppppppppppp.G........",
                "...........ppppqqqppppG........",
                "...........qq.qqqqq.qqG........",
            ],
            "walk_b": [
                "......................O........",
                ".....................OWO.......",
                "......................O........",
                "...............q...............",
                "..............ppp..............",
                ".............ppppp.............",
                "............pPpppPp...G........",
                "...........ppPpppPpp..G........",
                "...........pbbbbbbbp..G........",
                ".........qqqqqqqqqqqqqG........",
                "............sssssss...G........",
                "............sksssks...G........",
                "...........wwwwwwwww..G........",
                ".........ppppwwwwwppppG........",
                ".........ppPpwwwwwpPppG........",
                ".........pbbbbbbbbbbbpG........",
                ".........ppppPpppPppppG........",
                "..........ppppppppppp.G........",
                ".........ppppqqqpppp..G........",
                ".........qq.qqqqq.qq..G........",
            ],
            "dash": [
                ".........................O.....",
                "........................OWO....",
                ".........................O.....",
                "..................q............",
                "................ppp............",
                "...............ppppp...........",
                "..............pPpppPp...G......",
                ".............ppPpppPpp..G......",
                ".............pbbbbbbbp..G......",
                "...........qqqqqqqqqqqqqG......",
                ".............sssssss...G.......",
                ".............sksssks...G.......",
                "............wwwwwwwww..G.......",
                "..........ppppwwwwwppppG.......",
                "..........ppPpwwwwwpPppG.......",
                "..........pbbbbbbbbbbbpG.......",
                ".........ppppPpppPppppG........",
                "..........ppppppppppp.G........",
                "...........ppppqqqppppG........",
                "...........qq.qqqqq.qqG........",
            ],
            "hurt": [
                "....................O..........",
                "...................OWO.........",
                "....................O..........",
                ".............q.................",
                "............ppp................",
                "............ppppp..............",
                "...........pPpppPp...G.........",
                "..........ppPpppPpp..G.........",
                "..........pbbbbbbbp..G.........",
                "........qqqqqqqqqqqqqG.........",
                "...........sssssss...G.........",
                "...........sksssks...G.........",
                "..........wwwwwwwww..G.........",
                "........ppppwwwwwppppG.........",
                "........ppPpwwwwwpPppG.........",
                ".........pbbbbbbbbbbbpG........",
                ".........ppppPpppPppppG........",
                "..........ppppppppppp.G........",
                "..........ppppqqqpppp.G........",
                "..........qq.qqqqq.qq.G........",
            ],
            "attack1": [
                ".......................O.......",
                "......................OWO......",
                ".......................O.......",
                "...............q.......O.......",
                "..............ppp......O.......",
                ".............ppppp.............",
                "............pPpppPp............",
                "...........ppPpppPpp...........",
                "...........pbbbbbbbp...G.......",
                ".........qqqqqqqqqqqqq.G.......",
                "............sssssss....G.......",
                "............sksssks...sG.......",
                "...........wwwwwwwww..p........",
                ".........ppppwwwwwpppp.........",
                ".........ppPpwwwwwpPpp.........",
                ".........pbbbbbbbbbbbp.........",
                ".........ppppPpppPpppp.........",
                "..........ppppppppppp..........",
                "..........ppppqqqpppp..........",
                "..........qq.qqqqq.qq..........",
            ],
            "attack2": [
                "...............................",
                "...............................",
                "...............................",
                "................q..............",
                "...............ppp.............",
                "..............ppppp............",
                ".............pPpppPp...........",
                "............ppPpppPpp..........",
                "............pbbbbbbbp..........",
                "..........qqqqqqqqqqqqq.......O",
                "............sssssss..psGGGGGOWO",
                "............sksssks..p.......O.",
                "...........wwwwwwwww...........",
                ".........ppppwwwwwpppp.........",
                ".........ppPpwwwwwpPpp.........",
                ".........pbbbbbbbbbbbp.........",
                ".........ppppPpppPpppp.........",
                "..........ppppppppppp..........",
                "..........ppppqqqpppp..........",
                "..........qq.qqqqq.qq..........",
            ],
        },
    },
}
for _cid, _art in PLAYER_ART.items():
    for _name, _rows in _art["frames"].items():
        SPRITE_DATA["%s_%s" % (_cid, _name)] = (_rows, _art["pal"])

SPRITE_DATA.update({
    "emerald": (
        [
            ".LLLgg.",
            "LLwLggd",
            "LLLggdd",
            "LLgggdd",
            "LLgggdd",
            "LgggddD",
            "LgggdDD",
            ".ggddD.",
        ],
        {'L': '#a6f2c4', 'g': '#4fd08a', 'd': '#2a8f5c', 'D': '#1c6a44', 'w': '#ffffff'},
    ),
    "ruby": (
        [
            "..LLg..",
            ".LwLgd.",
            "LLLggdd",
            ".LLggd.",
            "..Lgdd.",
            "..ggd..",
            "...d...",
        ],
        {'L': '#ffa8b8', 'g': '#ff4d6d', 'd': '#a82a44', 'w': '#ffffff'},
    ),
})


SPRITE_DATA.update({
    "coin_a": (
        [
            "..yod..",
            ".yoood.",
            "yyododd",
            "yyododd",
            "ooododd",
            ".ooood.",
            "..ddd..",
        ],
        {'y': '#fff0a0', 'o': '#ffd34d', 'd': '#c98a1a'},
    ),
    "coin_b": (
        [
            "...o...",
            "..yod..",
            "..yoo..",
            ".yyood.",
            "..ooo..",
            "..ood..",
            "...d...",
        ],
        {'y': '#fff0a0', 'o': '#ffd34d', 'd': '#c98a1a'},
    ),
    "coin_c": (
        [
            "...o...",
            "...o...",
            "...o...",
            "...o...",
            "...o...",
            "...o...",
            "...d...",
        ],
        {'y': '#fff0a0', 'o': '#ffd34d', 'd': '#c98a1a'},
    ),
})

SPRITE_DATA.update({
    "firepit": (
        [
            "..sSsSSssSSsSs..",
            ".sSddbbbbbbddSs.",
            "sSdblLlLLlLlbdSs",
            "sdbLlLlLLlLlLbds",
            "sSdbbLlLLlLbbdSs",
            ".sSddbbbbbbddSs.",
            "..sdSsSSSSsSds..",
        ],
        {'s': '#6b6480', 'S': '#8a829e', 'd': '#3a3450', 'b': '#2a1810', 'l': '#7a4a2a', 'L': '#a86a3a'},
    ),
    "fire_a": (
        [
            "....r....",
            "...ror...",
            "...oor...",
            "..rooor..",
            "..oooyor.",
            ".rooyyoor",
            ".ooyyyoor",
            ".oyywyyoo",
            ".oyywyyo.",
            "..oyyyo..",
            "...ooo...",
        ],
        {'r': '#e8452a', 'o': '#ff8a2a', 'y': '#ffd34d', 'w': '#fff0a8'},
    ),
    "fire_b": (
        [
            "...r.....",
            "...ro....",
            "..roor...",
            "..rooor..",
            "..ooyoor.",
            ".rooyyoor",
            ".ooyyyoo.",
            ".oyywyyoo",
            ".oyywyyo.",
            "..oyyyo..",
            "...ooo...",
        ],
        {'r': '#e8452a', 'o': '#ff8a2a', 'y': '#ffd34d', 'w': '#fff0a8'},
    ),
    "fire_c": (
        [
            ".....r...",
            "....ror..",
            "...roor..",
            "...rooor.",
            "..rooyoor",
            ".rooyyoo.",
            ".ooyyyoor",
            ".oyywyyoo",
            ".oyywyyo.",
            "..oyyyo..",
            "...ooo...",
        ],
        {'r': '#e8452a', 'o': '#ff8a2a', 'y': '#ffd34d', 'w': '#fff0a8'},
    ),
    "well": (
        [
            "..ssssssssssss..",
            ".sSSSSSSSSSSSSs.",
            "sSwwwwwwwwwwwwSs",
            "sSwWWwwwwwwWWwSs",
            "sSwwwwwwwwwwwwSs",
            "sSwwwwwwwwwwwwSs",
            ".sSSSSSSSSSSSSs.",
            ".sSssdSssSdssSs.",
            ".sdssSSssSSssds.",
            ".ssSSssddssSSss.",
            ".sSSsdsSSsdsSSs.",
            "..ssssssssssss..",
        ],
        {'s': '#6b6480', 'S': '#8a829e', 'd': '#4a4460', 'w': '#1f3a6e', 'W': '#5a8ad0'},
    ),
    "crate": (
        [
            "dddddddddd",
            "dLLLLLLLLd",
            "dLdLLLLdLd",
            "dLLdLLdLLd",
            "dLLLddLLLd",
            "dLLdLLdLLd",
            "dLdLLLLdLd",
            "dLLLLLLLLd",
            "dddddddddd",
        ],
        {'d': '#5a3a1a', 'L': '#8a5a2b'},
    ),
    "barrel": (
        [
            "..bbbbb..",
            ".bLLLLLb.",
            "bLLLLLLLb",
            "hhhhhhhhh",
            "bLLlLLLLb",
            "bLLLLlLLb",
            "bLLLLLLLb",
            "hhhhhhhhh",
            ".bLLLLLb.",
            "..bbbbb..",
        ],
        {'b': '#5a3a1a', 'L': '#8a5a2b', 'l': '#b07a3b', 'h': '#6a6a7a'},
    ),
    "sign": (
        [
            "dddddddddddd",
            "dLLLLLLLLLLd",
            "dLtttLtttLLd",
            "dLLLLLLLLLLd",
            "dLtttttLtttd",
            "dLLLLLLLLLLd",
            "dLtttLttLLLd",
            "dLLLLLLLLLLd",
            "dddddddddddd",
            ".....pp.....",
            ".....pp.....",
            ".....pp.....",
            ".....pp.....",
            ".....pp.....",
            ".....pp.....",
            "....pppp....",
        ],
        {'d': '#5a3a1a', 'L': '#a87a45', 't': '#5a3a1a', 'p': '#6a4426'},
    ),
    "dummy": (
        [
            "..hhhhhhh..",
            ".hhhhhhhhh.",
            ".hkhhhhhkh.",
            ".hhhhhhhhh.",
            "..HHHHHHH..",
            "...sssss...",
            "wwwwwwwwwww",
            "..sRRRRRs..",
            "..sRRRRRs..",
            "..sRRRRRs..",
            "..sRRRRRs..",
            "...sssss...",
            "....WWW....",
            "....WWW....",
            "....WWW....",
            "....WWW....",
            "...WWWWW...",
        ],
        {'h': '#d2b078', 'H': '#a98a4a', 'k': '#1a1626', 's': '#e8c860', 'R': '#b02a3a', 'w': '#8a5a2b', 'W': '#6a4426'},
    ),
    "shop": (
        [
            "..rrrrrrrrrrrrrr..",
            ".rrRRrrRRrrRRrrRr.",
            "rrRRrrRRrrRRrrRRrr",
            "RRrrRRrrRRrrRRrrRR",
            "..bb..........bb..",
            "..bb..cccccc..bb..",
            "..bb.cCoGoCc.bb...",
            "..bb.cCoooCc.bb...",
            "..bb..cccccc.bb...",
            "..bb..........bb..",
            ".wwwwwwwwwwwwwwww.",
            "wLLLLLLLLLLLLLLLLw",
            "wLwLwLwLwLwLwLwLLw",
            "wwwwwwwwwwwwwwwwww",
        ],
        {'r': '#8e2a36', 'R': '#d9563a', 'b': '#4a2f1a', 'c': '#2a1638', 'C': '#5a3a1a', 'o': '#e8c860', 'G': '#fff3c4', 'w': '#6a4426', 'L': '#8a5a2b'},
    ),
    "brazier": (
        [
            ".bbbbbbbbb.",
            "bDDDDDDDDDb",
            "bDDDDDDDDDb",
            ".bDDDDDDDb.",
            "..bbbbbbb..",
            "...ppppp...",
            "...ppppp...",
            "...ppppp...",
            "..ppppppp..",
            ".ppppppppp.",
        ],
        {'b': '#3a3450', 'D': '#1a1220', 'p': '#4a4460'},
    ),
})

# ----------------------------------------------------------------------------
# Sound: tiny synthesised beeps (no sound files needed)
# ----------------------------------------------------------------------------
RATE = 22050


def open_mixer():
    """Open the audio device as mono 16-bit 22 kHz (SDL converts for the speakers)."""
    try:
        pygame.mixer.init(frequency=RATE, size=-16, channels=1, buffer=512, allowedchanges=0)
    except TypeError:
        pygame.mixer.init(frequency=RATE, size=-16, channels=1, buffer=512)


def to_mixer(pcm):
    """Convert mono 16-bit 22 kHz samples to the format the mixer really opened with."""
    init = pygame.mixer.get_init()
    if not init:
        return pcm
    freq, fmt, chans = init
    if fmt != -16 or (freq == RATE and chans == 1):
        return pcm
    samples = array.array("h")
    samples.frombytes(pcm)
    if freq != RATE:
        ratio = freq / RATE
        last = len(samples) - 1
        samples = array.array("h", [samples[min(last, int(i / ratio))] for i in range(int(len(samples) * ratio))])
    if chans == 2:
        out = array.array("h", [0]) * (len(samples) * 2)
        out[0::2] = samples
        out[1::2] = samples
        samples = out
    return samples.tobytes()


class Sfx:
    SPECS = {
        "start": (330, 0.12, "triangle", 0.05, 200),
        "select": (500, 0.05, "square", 0.04, 0),
        "slash": (420, 0.10, "square", 0.04, -260),
        "dash": (250, 0.14, "triangle", 0.06, 300),
        "hurt": (150, 0.28, "saw", 0.07, -90),
        "hit": (300, 0.08, "square", 0.05, -120),
        "kill": (200, 0.18, "square", 0.06, 260),
        "clear": (520, 0.30, "triangle", 0.06, 400),
        "bolt": (640, 0.14, "triangle", 0.05, -380),
    }
    # sounds made of several notes played one after another
    SEQUENCES = {
        "coin": [(988, 0.05, "square", 0.04, 0), (1319, 0.16, "square", 0.04, -150)],
        "emerald": [(1047, 0.05, "square", 0.04, 0), (1319, 0.05, "square", 0.04, 0), (1568, 0.16, "square", 0.04, -150)],
        "ruby": [(1319, 0.06, "square", 0.04, 0), (1568, 0.06, "square", 0.04, 0),
                 (1976, 0.06, "square", 0.04, 0), (2637, 0.26, "square", 0.04, -300)],
    }

    def __init__(self):
        self.ok = False
        self.muted = False
        self.volume = 1.0
        self.sounds = {}
        try:
            open_mixer()
            self.ok = True
        except pygame.error:
            return
        for name, (f, d, kind, v, slide) in self.SPECS.items():
            self.sounds[name] = self._tone(f, d, kind, v * 2.5, slide)
        for name, notes in self.SEQUENCES.items():
            self.sounds[name] = self._sequence(notes)

    @staticmethod
    def _samples(freq, dur, kind, vol, slide):
        n = int(RATE * dur)
        buf = array.array("h")
        phase = 0.0
        end = max(30.0, freq + slide)
        for i in range(n):
            t = i / n
            f = freq * (end / freq) ** t if slide else freq
            phase += f / RATE
            p = phase % 1.0
            if kind == "square":
                s = 1.0 if p < 0.5 else -1.0
            elif kind == "triangle":
                s = 4.0 * abs(p - 0.5) - 1.0
            else:
                s = 2.0 * p - 1.0
            env = 0.0001 ** t
            buf.append(int(s * env * vol * 32767))
        return buf

    @classmethod
    def _tone(cls, freq, dur, kind, vol, slide):
        return pygame.mixer.Sound(buffer=to_mixer(cls._samples(freq, dur, kind, vol, slide).tobytes()))

    @classmethod
    def _sequence(cls, notes):
        joined = array.array("h")
        for (freq, dur, kind, v, slide) in notes:
            joined.extend(cls._samples(freq, dur, kind, v * 2.5, slide))
        return pygame.mixer.Sound(buffer=to_mixer(joined.tobytes()))

    def set_volume(self, v):
        self.volume = clamp(v, 0.0, 1.0)
        for snd in self.sounds.values():
            snd.set_volume(self.volume)

    def play(self, name):
        if self.ok and not self.muted:
            self.sounds[name].play()


class Music:
    """Plays the composed loop on its own mixer channel, with its own volume."""
    GAIN = 0.8

    def __init__(self):
        self.ok = False
        self.sound = None
        self.channel = None
        self.volume = 0.55
        self.muted = False
        self.paused = False
        self._pcm = None
        if not pygame.mixer.get_init():
            return
        try:
            pygame.mixer.set_reserved(1)           # channel 0 is kept for the music
            self.channel = pygame.mixer.Channel(0)
        except pygame.error:
            return
        self.ok = True
        threading.Thread(target=self._compose, daemon=True).start()

    def _compose(self):
        try:
            self._pcm = to_mixer(compose_dark_fantasy())
        except Exception:
            self._pcm = None

    def update(self):
        """Start the loop as soon as the background composer has finished."""
        if self.ok and self.sound is None and self._pcm:
            self.sound = pygame.mixer.Sound(buffer=self._pcm)
            self._pcm = None
            self.channel.play(self.sound, loops=-1, fade_ms=1500)
            self._apply()
            if self.paused:
                self.channel.pause()

    def _apply(self):
        if self.ok:
            self.channel.set_volume(0.0 if self.muted else clamp(self.volume, 0.0, 1.0) * self.GAIN)

    def set_volume(self, v):
        self.volume = v
        self._apply()

    def set_muted(self, muted):
        self.muted = muted
        self._apply()

    def set_paused(self, paused):
        if paused == self.paused:
            return
        self.paused = paused
        if self.ok and self.sound is not None:
            if paused:
                self.channel.pause()
            else:
                self.channel.unpause()


# ----------------------------------------------------------------------------
# Music: a dark-fantasy chiptune loop composed from code. It uses the voices of an old
# 8-bit console (thin pulse waves, a stepped triangle bass and LFSR noise drums) and is
# generated in the background at start-up, so no audio files are needed.
# ----------------------------------------------------------------------------
def compose_dark_fantasy():
    BPM = 104
    beat = 60.0 / BPM
    bars = 16

    def S(beats):
        return int(round(RATE * beat * beats))

    total = S(bars * 4)
    tail = S(3.0)
    size = total + tail
    cache = {}

    def mtof(m):
        return 440.0 * 2 ** ((m - 69) / 12.0)

    def breathe():
        time.sleep(0.001)   # keep the game window smooth while this builds in the background

    def envelope(n, attack, release, decay_to):
        key = ("e", n, attack, release, decay_to)
        e = cache.get(key)
        if e is None:
            e = []
            for i in range(n):
                if i < attack:
                    v = i / max(1, attack)
                else:
                    v = 1.0 - (1.0 - decay_to) * ((i - attack) / max(1, n - attack))
                left = n - i
                if left < release:
                    v *= left / release
                e.append(round(v * 15) / 15.0)      # 4-bit volume steps, like a sound chip
            cache[key] = e
        return e

    def pulse(freq, n, duty, attack=30, release=120, decay_to=1.0):
        period = max(2, int(round(RATE / freq)))
        key = ("p", period, n, duty, attack, release, decay_to)
        w = cache.get(key)
        if w is None:
            hi = max(1, int(period * duty))
            mean = (hi - (period - hi)) / period          # remove the DC offset of uneven pulses (avoids clicks)
            cyc = [1.0 - mean] * hi + [-1.0 - mean] * (period - hi)
            base = (cyc * (n // period + 2))[:n]
            w = [a * b for a, b in zip(base, envelope(n, attack, release, decay_to))]
            cache[key] = w
        return w

    def tri(freq, n, attack=60, release=250):
        period = max(4, int(round(RATE / freq)))
        key = ("t", period, n, attack, release)
        w = cache.get(key)
        if w is None:
            cyc = [round((4.0 * abs(i / period - 0.5) - 1.0) * 7.5) / 7.5 for i in range(period)]
            base = (cyc * (n // period + 2))[:n]
            w = [a * b for a, b in zip(base, envelope(n, attack, release, 1.0))]
            cache[key] = w
        return w

    def lead_note(freq, n, duty):
        """A singing pulse note with vibrato that fades in."""
        out = []
        ph = 0.0
        env = envelope(n, 200, 500, 0.7)
        two_pi = 6.283185307
        for i in range(n):
            t = i / RATE
            vib = 1.0 + 0.017 * min(1.0, t / 0.3) * math.sin(two_pi * 5.4 * t)
            ph += freq * vib / RATE
            out.append(((1.0 - (2 * duty - 1)) if (ph % 1.0) < duty else (-1.0 - (2 * duty - 1))) * env[i])
        return out

    def mix(buf, start, samples, gain):
        end = min(size, start + len(samples))
        if end <= start:
            return
        buf[start:end] = [a + b * gain for a, b in zip(buf[start:end], samples[: end - start])]

    def echo(buf, delay, gain, taps):
        src = buf[:]
        for k in range(1, taps + 1):
            d = delay * k
            g = gain ** k
            buf[d:] = [a + b * g for a, b in zip(buf[d:], src)]

    # ---- noise drums (a 15-bit shift register, like the old consoles) ----
    def lfsr(n, tap=1):
        reg = 1
        out = []
        for _ in range(n):
            bit = (reg ^ (reg >> tap)) & 1
            reg = (reg >> 1) | (bit << 14)
            out.append(1.0 if reg & 1 else -1.0)
        return out

    def make_kick():
        n = int(0.22 * RATE)
        out, ph = [], 0.0
        for i in range(n):
            t = i / n
            ph += (42 + 130 * (1 - t) ** 3) / RATE
            out.append(round(math.sin(6.283185 * ph) * (1 - t) ** 1.4 * 15) / 15.0)
        return out

    def make_snare():
        n = int(0.17 * RATE)
        noise = lfsr(n, 1)
        out = []
        for i in range(n):
            t = i / n
            tone = math.sin(6.283185 * 190 * (i / RATE)) * (1 - t) ** 3
            out.append(round((noise[i] * (1 - t) ** 2 * 0.8 + tone * 0.5) * 15) / 15.0)
        return out

    def make_hat(seconds):
        n = int(seconds * RATE)
        noise = lfsr(n, 6)
        return [round(noise[i] * (1 - i / n) ** 2.5 * 15) / 15.0 for i in range(n)]

    kick, snare = make_kick(), make_snare()
    hat_c, hat_o = make_hat(0.035), make_hat(0.11)

    # ---- harmony: D minor with a major A chord for tension ----
    CH = {
        "Dm": (38, [62, 65, 69, 74]),
        "Bb": (46, [58, 62, 65, 70]),
        "Gm": (43, [55, 58, 62, 67]),
        "A": (45, [57, 61, 64, 69]),
        "C": (48, [60, 64, 67, 72]),
    }
    prog_a = ["Dm", "Bb", "Gm", "A"]
    prog_b = ["Bb", "C", "Dm", "A"]
    order = prog_a + prog_a + prog_b + prog_a      # 16 bars

    # lead melodies: (beat in the bar, length in beats, midi note)
    mel_a = [[(0, 2, 69), (2, 1, 65), (3, 0.5, 67), (3.5, 0.5, 69)],
             [(0, 2, 70), (2, 1, 69), (3, 1, 67)],
             [(0, 1.5, 67), (1.5, 0.5, 69), (2, 1, 70), (3, 1, 74)],
             [(0, 2, 73), (2, 1, 74), (3, 1, 76)]]
    mel_b = [[(0, 1.5, 74), (1.5, 0.5, 72), (2, 2, 70)],
             [(0, 1, 67), (1, 1, 72), (2, 2, 76)],
             [(0, 2, 77), (2, 1, 76), (3, 1, 74)],
             [(0, 1.5, 73), (1.5, 0.5, 71), (2, 2, 69)]]
    mel_c = [[(0, 1, 74), (1, 1, 72), (2, 2, 69)],
             [(0, 1, 70), (1, 1, 74), (2, 2, 77)],
             [(0, 1, 74), (1, 1, 70), (2, 1, 67), (3, 1, 70)],
             [(0, 2, 73), (2, 2, 69)]]

    lead = [0.0] * size
    arp = [0.0] * size
    bass = [0.0] * size
    pad = [0.0] * size
    drums = [0.0] * size

    arp_pattern = [0, 1, 2, 3, 2, 1, 2, 3, 0, 1, 2, 3, 2, 1, 3, 2]
    for bar in range(bars):
        root, tones = CH[order[bar]]
        t0 = bar * 4.0

        # bass: slow pedal at first, then a driving eighth-note figure
        if bar < 2:
            for b in (0.0, 2.0):
                mix(bass, S(t0 + b), tri(mtof(root), int(S(2.0) * 0.96)), 1.0)
        else:
            for i, off in enumerate((0, 0, 12, 0, 0, 0, 12, 7)):
                mix(bass, S(t0 + i * 0.5), tri(mtof(root + off), int(S(0.5) * 0.92)), 1.0)

        # arpeggio: quick pulse "plucks" that shimmer over the chord
        vel = 0.75 if bar < 4 else 1.0
        for i, idx in enumerate(arp_pattern):
            mix(arp, S(t0 + i * 0.25), pulse(mtof(tones[idx]), int(S(0.25) * 0.85), 0.25, 8, 60, 0.3), vel)

        # pad: thin, hollow held tones
        for m in (tones[0], tones[2]):
            mix(pad, S(t0), pulse(mtof(m), int(S(4.0) * 0.98), 0.125, int(RATE * 0.4), int(RATE * 0.5), 0.75), 1.0)

        # drums start on bar 3 and thicken from bar 5
        if bar >= 2:
            full = bar >= 4
            kicks = (0, 8, 10) if full else (0, 8)
            for st in kicks:
                mix(drums, S(t0 + st * 0.25), kick, 0.55)
            if full:
                for st in (4, 12):
                    mix(drums, S(t0 + st * 0.25), snare, 0.32)
                for st in range(0, 16, 2):
                    mix(drums, S(t0 + st * 0.25), hat_o if st == 14 else hat_c, 0.10 if st % 4 else 0.14)
            else:
                for st in (0, 4, 8, 12):
                    mix(drums, S(t0 + st * 0.25), hat_c, 0.10)
            if bar == bars - 1:
                for st in (12, 13, 14, 15):
                    mix(drums, S(t0 + st * 0.25), snare, 0.28)
        breathe()

    # lead melody: a slow, haunting line over bars 5-16
    sections = [(4, mel_a, 0.5), (8, mel_b, 0.25), (12, mel_c, 0.5)]
    for first_bar, notes, duty in sections:
        for k in range(4):
            for (b, length, midi) in notes[k]:
                n = int(S(length) * 0.95)
                mix(lead, S((first_bar + k) * 4 + b), lead_note(mtof(midi), n, duty), 1.0)
            breathe()

    echo(lead, S(0.75), 0.40, 3)
    echo(arp, S(0.5), 0.30, 2)

    master = [l * 0.30 + a * 0.13 + b * 0.42 + p * 0.06 + d * 0.55
              for l, a, b, p, d in zip(lead, arp, bass, pad, drums)]
    head = master[:total]
    tail_part = master[total:]
    head[: len(tail_part)] = [a + b for a, b in zip(head[: len(tail_part)], tail_part)]   # seamless loop
    peak = max(max(head), -min(head)) or 1.0
    scale = 0.85 / peak
    pcm = array.array("h", [int(x * scale * 32767) for x in head])
    return pcm.tobytes()


# ----------------------------------------------------------------------------
# Dungeon
# ----------------------------------------------------------------------------
PIL = [(5, 3), (14, 3), (5, 8), (14, 8)]
PILSET = set(PIL)
_BORDER = {(x, y) for x in range(COLS) for y in range(ROWS) if x in (0, COLS - 1) or y in (0, ROWS - 1)}
DUNGEON_SOLID = _BORDER | PILSET
# the camp: things standing in the yard (kind, tile x, tile y), the training dummy and the gate
CAMP_OBJECTS = [("crate", 2, 2), ("crate", 3, 2), ("barrel", 2, 3), ("barrel", 17, 2), ("crate", 17, 3),
                ("brazier", 8, 2), ("brazier", 11, 2), ("firepit", 4, 7), ("well", 15, 8), ("sign", 7, 6),
                ("shop", 2, 5)]
CAMP_DUMMY = (15, 4)
CAMP_FIRE = (4 * T + 8, 7 * T + 8)
CAMP_SIGN = (7 * T + 8, 6 * T + 8)
CAMP_SHOP = (2 * T + 8, 5 * T + 8)
CAMP_SOLID = ((_BORDER - {(9, 0), (10, 0)}) | {(7, 1), (8, 1), (11, 1), (12, 1)}
              | {(tx, ty) for _, tx, ty in CAMP_OBJECTS} | {CAMP_DUMMY})
CURRENT_SOLID = DUNGEON_SOLID


def set_map(name):
    global CURRENT_SOLID
    CURRENT_SOLID = CAMP_SOLID if name == "camp" else DUNGEON_SOLID


def solid_tile(tx, ty):
    if tx < 0 or ty < 0 or tx >= COLS or ty >= ROWS:
        return True
    return (tx, ty) in CURRENT_SOLID


def collides(x, y, r):
    x0 = math.floor((x - r) / T)
    x1 = math.floor((x + r - 0.001) / T)
    y0 = math.floor((y - r) / T)
    y1 = math.floor((y + r - 0.001) / T)
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            if solid_tile(tx, ty):
                return True
    return False


def move_ent(e, dx, dy):
    nx = e.x + dx
    if not collides(nx, e.y, e.r):
        e.x = nx
    ny = e.y + dy
    if not collides(e.x, ny, e.r):
        e.y = ny


def build_background():
    """Chunky layer: drawn on a 160x96 grid, then scaled up 4x."""
    rng = random.Random(11)
    low = pygame.Surface((COLS * CT, ROWS * CT))

    def rect(x, y, w, h, c):
        low.fill(c, (x, y, w, h))

    def shade(x, y, w, h, a):
        low.blit(alpha_surf(w, h, (0, 0, 0), a), (x, y))

    dark = C("#171329")
    for ty in range(ROWS):
        for tx in range(COLS):
            x, y = tx * CT, ty * CT
            if tx == 0 or ty == 0 or tx == COLS - 1 or ty == ROWS - 1:
                rect(x, y, CT, CT, C("#2a2545"))
                rect(x, y + 1, CT, 1, C("#3a3360"))
                rect(x, y + 5, CT, 1, C("#3a3360"))
                rect(x, y, CT, 1, dark)
                rect(x, y + 4, CT, 1, dark)
                rect(x + 4, y + 1, 1, 3, dark)
                rect(x, y + 5, 1, 3, dark)
                if rng.random() < 0.3:
                    rect(x + 1 + int(rng.random() * 5), y + 1 + int(rng.random() * 2), 2, 1, C("#211d3a"))
            else:
                rect(x, y, CT, CT, C("#3a3560") if (tx + ty) & 1 else C("#363157"))
                for _ in range(3):
                    rect(x + int(rng.random() * 8), y + int(rng.random() * 8), 1, 1,
                         C("#2e2a4c") if rng.random() < 0.5 else C("#453f6c"))
                if rng.random() < 0.12:
                    cx = x + 1 + int(rng.random() * 4)
                    cy = y + 1 + int(rng.random() * 4)
                    c = C("#2b2748")
                    rect(cx, cy, 3, 1, c)
                    rect(cx + 2, cy + 1, 2, 1, c)
                    rect(cx + 3, cy + 2, 1, 2, c)
                shade(x, y, CT, 1, 0.12)
                shade(x, y, 1, CT, 0.12)
                if ty == 1:
                    shade(x, y, CT, 2, 0.28)
                if tx == 1:
                    shade(x, y, 2, CT, 0.20)
    for tx, ty in PIL:
        x, y = tx * CT, ty * CT
        shade(x + 1, y + CT, CT - 1, 1, 0.30)
        rect(x, y, CT, CT, dark)
        rect(x + 1, y + 1, CT - 2, 5, C("#6a63a0"))
        rect(x + 1, y + 1, CT - 2, 1, C("#7d76b6"))
        rect(x + 1, y + 6, CT - 2, 1, C("#443e6a"))
        rect(x + 2, y + 3, 2, 1, C("#57508a"))
    return pygame.transform.scale(low, (CW, CH))


def build_hub_background():
    """The camp: a cobbled courtyard inside the castle walls, with the dungeon gate at the top."""
    rng = random.Random(23)
    low = pygame.Surface((COLS * CT, ROWS * CT))

    def rect(x, y, w, h, c):
        low.fill(c, (x, y, w, h))

    def shade(x, y, w, h, a):
        low.blit(alpha_surf(w, h, (0, 0, 0), a), (x, y))

    dark = C("#171329")
    stones = [C("#4c4463"), C("#524a6a"), C("#463e5c"), C("#585070")]
    sand = [C("#6c5a5c"), C("#75625f"), C("#665456")]
    for ty in range(ROWS):
        for tx in range(COLS):
            x, y = tx * CT, ty * CT
            if tx in (0, COLS - 1) or ty in (0, ROWS - 1):
                rect(x, y, CT, CT, C("#4a3b52"))                      # castle wall, warmer than the dungeon's
                rect(x, y + 1, CT, 1, C("#66506a"))
                rect(x, y + 5, CT, 1, C("#66506a"))
                rect(x, y, CT, 1, dark)
                rect(x, y + 4, CT, 1, dark)
                rect(x + 4, y + 1, 1, 3, dark)
                rect(x, y + 5, 1, 3, dark)
                if rng.random() < 0.3:
                    rect(x + 1 + rng.randrange(5), y + 1 + rng.randrange(2), 2, 1, C("#3a2c42"))
                continue
            on_path = tx in (9, 10)
            rect(x, y, CT, CT, C("#4a3c40") if on_path else C("#2e2740"))          # mortar
            for (ox, oy) in ((0, 0), (4, 0), (0, 4), (4, 4)):                        # four cobbles per tile
                col = rng.choice(sand if on_path else stones)
                w = 3 + (rng.random() < 0.35)
                h = 3 + (rng.random() < 0.35)
                rect(x + ox, y + oy, w, h, col)
                low.set_at((x + ox, y + oy), lerp_color(col, (255, 255, 255), 0.12))
            if tx in (1, COLS - 2) or ty == ROWS - 2:                                # grass creeping in by the walls
                for _ in range(3):
                    if rng.random() < 0.7:
                        rect(x + rng.randrange(7), y + rng.randrange(7), 1, 2, C("#3f6a3a") if rng.random() < 0.6 else C("#325a30"))
            if ty == 1:
                shade(x, y, CT, 2, 0.30)
            if tx == 1:
                shade(x, y, 2, CT, 0.20)
            if tx == COLS - 2:
                shade(x + CT - 2, y, 2, CT, 0.20)
    # worn earth around the campfire and the training dummy
    for (cx, cy, r, col) in ((4 * CT + 4, 7 * CT + 4, 11, C("#5a4a4a")), (15 * CT + 4, 4 * CT + 4, 11, C("#66564f"))):
        pygame.draw.circle(low, col, (cx, cy), r)
        pygame.draw.circle(low, lerp_color(col, (0, 0, 0), 0.15), (cx, cy), r, 1)
    # banners hanging from the wall
    for tx in (3, 5, 14, 16):
        x = tx * CT + 2
        rect(x, 0, 4, 6, C("#a8323a"))
        rect(x, 0, 1, 6, C("#d9563a"))
        rect(x + 3, 0, 1, 6, C("#7a2230"))
        rect(x + 1, 6, 2, 1, C("#a8323a"))
        rect(x, 0, 4, 1, C("#e0a83c"))
    # the gatehouse: two stone towers and an arch with the glow of the dungeon inside
    for x0 in (7 * CT, 11 * CT):
        rect(x0, 0, 2 * CT, 2 * CT, C("#5c4a64"))
        rect(x0, 0, 3, 2 * CT, C("#463650"))
        rect(x0 + 2 * CT - 3, 0, 3, 2 * CT, C("#8a5a5a"))
        for yy in range(3, 2 * CT, 4):
            rect(x0, yy, 2 * CT, 1, C("#3a2c46"))
        rect(x0 + 6, 5, 2, 5, C("#160a1e"))
        rect(x0 + 6, 8, 2, 2, C("#ff9a3c"))
        rect(x0, 2 * CT - 1, 2 * CT, 1, C("#2a1c34"))
    rect(72, 0, 16, 16, C("#0e0716"))                                                # the dark passage
    rect(70, 0, 20, 3, C("#7a6a82"))                                                 # lintel
    rect(70, 3, 2, 13, C("#6a5a72"))
    rect(88, 3, 2, 13, C("#9a6a62"))
    rect(78, 0, 4, 3, C("#9a8aa2"))                                                  # keystone
    for i, yy in enumerate((12, 14)):
        rect(72 + i, yy, 16 - 2 * i, 1, C("#5a4a66"))                                # steps going down
    shade(70, 16, 20, 2, 0.25)
    return pygame.transform.scale(low, (CW, CH))


# ----------------------------------------------------------------------------
# Game data
# ----------------------------------------------------------------------------
CLASSES = [
    NS(id="knight", name="KNIGHT", hp=150, speed=82, cd=0.40, reach=40, arc=1.4, kb=190,
       dash_v=215, dash_cd=0.9, ranged=False,
       line1="STURDY KNIGHT", line2="150 HP, WIDE SWORD ARC"),
    NS(id="rogue", name="ROGUE", hp=100, speed=104, cd=0.24, reach=34, arc=1.0, kb=130,
       dash_v=280, dash_cd=0.5, ranged=False,
       line1="QUICK ROGUE", line2="100 HP, FAST, LONG DASH"),
    NS(id="mage", name="MAGE", hp=100, speed=88, cd=0.45, reach=0, arc=0, kb=110,
       dash_v=240, dash_cd=0.75, ranged=True,
       line1="RANGED MAGE", line2="100 HP, MAGIC BOLTS"),
]
DEF = {
    # coins=(chance to drop any, fewest, most); emerald / ruby = chance of also dropping that gem (far rarer than coins)
    "slime": dict(hp=2, r=7, speed=44, score=10, dmg=10, coins=(0.65, 1, 2), emerald=0.10, ruby=0.010),
    "bat": dict(hp=1, r=6, speed=64, score=15, dmg=5, coins=(0.5, 1, 1), emerald=0.08, ruby=0.015),
    "skel": dict(hp=2, r=6, speed=28, score=25, dmg=0, coins=(1.0, 2, 4), emerald=0.30, ruby=0.05),   # skeletons only hurt with arrows
}
GEM_VALUE = {"coin": 1, "emerald": 5, "ruby": 15}      # worth double this in score
GEM_COLORS = {"emerald": C("#4fd08a"), "ruby": C("#ff4d6d")}
MAGNET_RANGE = 34       # loot within this distance is pulled toward the player
PICKUP_LIFE = 14.0      # seconds before loot disappears
ARROW_DMG = 9           # a skeleton's arrow
WAVE_HEAL = 15          # health restored when a wave is cleared (the same for every class)
WAVE_CAP = 15            # clearing this wave ends the run and banks your loot at the camp shop
# permanent upgrades bought at the camp shop with banked loot, applied on top of the class's own stats
# "costs" gives a base price per currency at level 0; every level multiplies each by "growth"
UPGRADES = [
    dict(id="vitality", label="VITALITY", costs={"coins": 8}, icon="heart", max_level=5,
         growth=1.7, effect="+15 MAX\nHEALTH"),
    dict(id="sharpness", label="SHARPNESS", costs={"emeralds": 2, "rubies": 1}, icon="bolt", max_level=5,
         growth=1.6, effect="FASTER\nATTACKS"),
    dict(id="swiftness", label="SWIFTNESS", costs={"emeralds": 3}, icon="boot", max_level=5,
         growth=1.6, effect="MORE MOVE\nSPEED"),
]
# one unique upgrade per class, shown alongside the three above when that class is selected
CLASS_UPGRADES = {
    "knight": dict(id="knight_bulwark", label="BULWARK", costs={"coins": 15, "emeralds": 2}, icon="shield",
                   max_level=3, growth=1.7, effect="WIDER SWING\nMORE KNOCKBACK"),
    "rogue": dict(id="rogue_shadowstep", label="SHADOWSTEP", costs={"coins": 10, "emeralds": 2}, icon="dash",
                  max_level=3, growth=1.7, effect="FASTER DASH\nRECOVERY"),
    "mage": dict(id="mage_arcane", label="ARCANE BOLT", costs={"coins": 10, "emeralds": 3}, icon="star",
                 max_level=3, growth=1.7, effect="BOLTS PIERCE\n+1 ENEMY"),
}
ALL_UPGRADES = UPGRADES + list(CLASS_UPGRADES.values())
CUR_COLOR = {"coins": C("#ffd34d"), "emeralds": C("#a6f2c4"), "rubies": C("#ffa8b8")}
CUR_ICON = {"coins": "coin_a", "emeralds": "emerald", "rubies": "ruby"}
CUR_SFX = {"coins": "coin", "emeralds": "emerald", "rubies": "ruby"}


def upgrade_cost(u, level):
    """{currency: amount} owed for the next level of this upgrade."""
    return {cur: int(math.ceil(base * u["growth"] ** level)) for cur, base in u["costs"].items()}


def primary_currency(u):
    return next(iter(u["costs"]))
BURST_COLORS = {"slime": C("#4fd08a"), "bat": C("#8b5fd0"), "skel": C("#e8e2cf")}

CARD_W, CARD_GAP, CARD_X0, CARD_Y, CARD_H = 92, 6, 16, 54, 72


def card_x(i):
    return CARD_X0 + i * (CARD_W + CARD_GAP)


# arrow pixels: (distance behind the tip, sideways offset, colour)
ARROW_PX = [(d, 0, C("#c9b48a")) for d in range(11)]
ARROW_PX += [(0, 0, C("#e8f0ff")), (1, 0, C("#e8f0ff")), (1, -1, C("#e8f0ff")), (1, 1, C("#e8f0ff")),
             (2, 0, C("#e8f0ff")), (2, -1, C("#c8d2e6")), (2, 1, C("#c8d2e6"))]
ARROW_PX += [(9, -1, C("#ff5a7a")), (9, 1, C("#ff5a7a")), (10, -1, C("#ff5a7a")), (10, 1, C("#ff5a7a"))]


# ----------------------------------------------------------------------------
# Title screen artwork: a castle on a crag, a mountain and an orange sunset.
# Painted from code on a 320x192 pixel grid (2 canvas px per pixel).
# ----------------------------------------------------------------------------
SKY_STOPS = [C(h) for h in ("#120a2e", "#2a1350", "#5b2568", "#a03a62", "#d24a4a", "#ee6a34", "#ff9a3c", "#ffc060")]
BAYER4 = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))
SUN = (180, 110, 28)  # x, y, radius
CASTLE_COL = C("#120820")
# lit windows: (x, y, flicker speed, phase, kind)  kind: "w" = arched window, "s" = arrow slit
WINDOWS = [(109, 84, 0.0, 0, "w"), (122, 84, 1.4, 1.0, "w"), (135, 84, 0.0, 0, "w"),
           (112, 95, 0.0, 0, "w"), (132, 95, 2.0, 3.0, "w"),
           (122, 60, 0.0, 0, "w"), (122, 67, 1.9, 2.0, "w"),
           (87, 74, 0.0, 0, "s"), (87, 86, 1.6, 0.4, "s"), (87, 98, 0.0, 0, "s"),
           (63, 96, 0.0, 0, "s"), (64, 104, 1.2, 4.0, "s"),
           (152, 76, 0.0, 0, "w"), (152, 88, 1.1, 3.0, "w"), (152, 99, 0.0, 0, "w"),
           (165, 98, 1.7, 5.0, "w"), (171, 98, 0.0, 0, "w")]
WALL_TORCHES = [(71, 103), (156, 108), (177, 107), (104, 100)]
LANTERNS = [(146, 111), (165, 117), (169, 131), (155, 141)]
CLOUDS = [(52, 86, 9, 3.0, 40), (74, 64, 8, 4.5, 210), (96, 110, 7, 2.2, 120), (38, 70, 6, 5.5, 290)]
TORCHES = [(254, 174), (286, 174)]


def _make_cloud(w, h, rng):
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    for row in range(h):
        span = w * 0.5 * (math.sin(math.pi * (row + 0.5) / h) ** 0.55)
        span += rng.randint(-2, 2)
        x0, x1 = int(w / 2 - span), int(w / 2 + span)
        top = row < h * 0.5
        col = C("#ffc08a") if row < h * 0.25 else (C("#ff9a6a") if top else (C("#c85a7c") if row < h * 0.8 else C("#8a3a6a")))
        surf.fill(col, (x0, row, max(1, x1 - x0), 1))
    return surf


def draw_big_title(surf, s, cx, y, scale):
    """Gold-to-orange title lettering with a dark outline and drop shadow."""
    w = text_width(s, scale)
    x0 = int(cx * SC) - w // 2
    py = int(y * SC)
    for ch_i, ch in enumerate(s):
        x = x0 + ch_i * 6 * scale
        surf.blit(glyph(ch, scale, C("#2a0a18")), (x + scale, py + 2 * scale))
    for ch_i, ch in enumerate(s):
        x = x0 + ch_i * 6 * scale
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
            surf.blit(glyph(ch, scale, OUTLINE), (x + dx * scale, py + dy * scale))
    for ch_i, ch in enumerate(s):
        x = x0 + ch_i * 6 * scale
        surf.blit(glyph(ch, scale, C("#ffe89a")), (x, py), pygame.Rect(0, 0, 5 * scale, 3 * scale))
        surf.blit(glyph(ch, scale, C("#ffb640")), (x, py + 3 * scale), pygame.Rect(0, 3 * scale, 5 * scale, 2 * scale))
        surf.blit(glyph(ch, scale, C("#f0762a")), (x, py + 5 * scale), pygame.Rect(0, 5 * scale, 5 * scale, 2 * scale))


class TitleScene:
    def __init__(self):
        rng = random.Random(21)
        sky = pygame.Surface((W, H))
        n = len(SKY_STOPS) - 1
        horizon = 146
        for y in range(H):
            v = (min(1.0, y / horizon) ** 0.9) * n
            base = int(v)
            frac = v - base
            for x in range(W):
                thr = (BAYER4[y & 3][x & 3] + 0.5) / 16
                sky.set_at((x, y), SKY_STOPS[min(base + (1 if frac > thr else 0), n)])
        # the sun, with a dithered glow around it
        sx, sy, sr = SUN
        warm = C("#ffb347")
        for y in range(max(0, sy - sr - 40), min(H, sy + sr + 40)):
            for x in range(max(0, sx - sr - 60), min(W, sx + sr + 60)):
                d = math.hypot(x - sx, y - sy)
                if d <= sr:
                    sky.set_at((x, y), C("#fffbd6") if d < sr * 0.5 else (C("#fff0a0") if d < sr * 0.8 else C("#ffd970")))
                elif d < sr + 34:
                    if (1 - (d - sr) / 34) * 0.85 > (BAYER4[y & 3][x & 3] + 0.5) / 16:
                        sky.set_at((x, y), warm)
        self.sky = pygame.transform.scale(sky, (CW, CH)).convert()

        land = pygame.Surface((W, H), pygame.SRCALPHA)

        def poly(pts, col):
            pygame.draw.polygon(land, col, pts)

        def rect(x, y, w, h, col):
            land.fill(col, (x, y, w, h))

        # hazy far ridge and distant peaks
        pts = [(0, 150)]
        for x in range(0, 321, 4):
            pts.append((x, int(122 + 7 * math.sin(x * 0.045) + 4 * math.sin(x * 0.13 + 2) + rng.randint(-1, 1))))
        pts.append((320, 150))
        poly(pts, C("#8a3f72"))
        poly([(-10, 150), (10, 126), (22, 112), (32, 98), (40, 110), (48, 104), (60, 120), (74, 128), (90, 150)], C("#5a2a66"))
        poly([(32, 98), (40, 110), (48, 104), (60, 120), (74, 128), (90, 150), (48, 150), (36, 116)], C("#7b3a70"))
        # the big mountain: sunlit left face, shadowed right face, snowy top
        left = [(150, 150), (166, 138), (176, 130), (186, 116), (196, 108), (206, 92), (214, 82), (222, 68), (229, 56), (236, 44)]
        right = [(243, 55), (249, 63), (255, 61), (262, 76), (270, 87), (276, 99), (286, 107), (294, 119), (304, 125), (320, 137), (320, 150)]
        lit_col, dark_col = C("#8f4573"), C("#4a2262")
        poly(left + right, dark_col)
        ridge = [(236, 44), (233, 60), (238, 74), (229, 92), (236, 108), (225, 126), (232, 150)]
        poly(left + ridge[1:], lit_col)
        for (x1, y1, x2, y2) in [(222, 68, 214, 104), (206, 92, 200, 124), (216, 100, 212, 140), (196, 108, 190, 134)]:
            pygame.draw.line(land, C("#7a3562"), (x1, y1), (x2, y2))
        for (x1, y1, x2, y2) in [(243, 55, 250, 92), (256, 64, 262, 110), (270, 87, 276, 128), (286, 107, 290, 140)]:
            pygame.draw.line(land, C("#3a1a52"), (x1, y1), (x2, y2))
        for x in range(190, 290):
            for y in range(42, 86):
                px = land.get_at((x, y))
                if px[3] == 0:
                    continue
                col = (px[0], px[1], px[2])
                jag = rng.randint(-1, 1)
                if col == lit_col and y < 72 + 3 * math.sin(x * 0.5) + jag:
                    land.set_at((x, y), C("#ffd9bd"))
                elif col == dark_col and y < 66 + 3 * math.sin(x * 0.7) + jag:
                    land.set_at((x, y), C("#b48aae"))
        # a rocky spur of the mountain with terraces and cliff faces, lit on its sunward side
        rock_dark, rock_mid, rock_lit = C("#2b1640"), C("#40244f"), C("#7a4058")
        crag = [(28, 152), (38, 144), (44, 134), (48, 124), (50, 116), (52, 112), (98, 112), (100, 104), (148, 104),
                (150, 110), (182, 110), (186, 120), (191, 130), (198, 140), (212, 152)]
        poly(crag, rock_dark)
        poly([(182, 110), (186, 120), (191, 130), (198, 140), (212, 152), (200, 152), (192, 141), (185, 129), (180, 117)], rock_lit)
        for (x0, x1, ytop, ymax) in [(52, 98, 112, 30), (100, 148, 104, 34), (150, 182, 110, 28)]:
            for x in range(x0, x1, 3):
                pygame.draw.line(land, rock_mid, (x, ytop), (x + rng.randint(-2, 2), ytop + rng.randint(10, ymax)))
            for x in range(x0 + 1, x1, 5):
                land.set_at((x, ytop + rng.randint(4, 12)), rock_lit)
            pygame.draw.line(land, C("#c07a4a"), (x0, ytop), (x1 - 1, ytop))          # sunlit edge of the terrace
        for _ in range(110):
            cx_, cy_ = rng.randint(104, 206), rng.randint(114, 148)
            if tuple(land.get_at((cx_, cy_)))[:3] == rock_dark:
                rect(cx_, cy_, rng.randint(1, 3), 1, rock_lit if cx_ > 150 else rock_mid)
        for (x1, y1, x2, y2) in [(34, 146, 46, 132), (40, 140, 50, 124), (44, 134, 52, 118)]:
            pygame.draw.line(land, rock_mid, (x1, y1), (x2, y2))

        stone_mid, stone_dark, stone_lit = C("#58355a"), C("#3a2044"), C("#a45b45")
        mortar_mid, mortar_dark, mortar_lit = C("#3c2244"), C("#2a1633"), C("#7c403d")

        def stone(x, y, w, h):
            """A masonry wall lit from the right: dark on the left, warm on the right."""
            band = max(2, w // 4)
            rect(x, y, w, h, stone_mid)
            rect(x, y, band, h, stone_dark)
            rect(x + w - band, y, band, h, stone_lit)
            for yy in range(y + 3, y + h, 4):
                rect(x, yy, band, 1, mortar_dark)
                rect(x + band, yy, w - 2 * band, 1, mortar_mid)
                rect(x + w - band, yy, band, 1, mortar_lit)
            for _ in range(w * h // 28):
                px, py = x + rng.randrange(w), y + rng.randrange(h)
                land.set_at((px, py), mortar_mid if px < x + band else (C("#c27a55") if px >= x + w - band else C("#6c4470")))
            rect(x + w - 1, y, 1, h, C("#ffb060"))                                        # rim light on the sunward edge

        def battlement(x, y, w):
            for i in range(0, w - 2, 5):
                rect(x + i, y, 3, 3, stone_mid)
                rect(x + i + 2, y, 1, 3, stone_lit)
                rect(x + i, y, 3, 1, C("#e0925a"))                                        # sun catches the tops

        def cone(cx, base_y, half_w, apex_y, dark=C("#2a1838"), lit=C("#8a4050")):
            poly([(cx - half_w, base_y), (cx, base_y), (cx, apex_y)], dark)
            poly([(cx, base_y), (cx + half_w, base_y), (cx, apex_y)], lit)
            pygame.draw.line(land, C("#ffb060"), (cx, apex_y), (cx + half_w, base_y))
            rect(cx, apex_y - 2, 1, 3, C("#e0925a"))

        def drum(x, y, w, h):
            """A round tower: shaded like a cylinder."""
            for i in range(w):
                t = (i / (w - 1)) ** 1.4
                col = lerp_color(C("#33203f"), C("#b8683f"), t)
                rect(x + i, y, 1, h, col)
            for yy in range(y + 3, y + h, 4):
                rect(x, yy, w, 1, C("#2a1633"))
            for _ in range(w * h // 26):
                land.set_at((x + rng.randrange(w), y + rng.randrange(h)), C("#6a4468"))

        # small gabled hall behind the right wall, with a chimney
        rect(160, 86, 18, 22, stone_mid)
        rect(160, 86, 4, 22, stone_dark)
        rect(174, 86, 4, 22, stone_lit)
        poly([(158, 86), (168, 86), (168, 75)], C("#2a1838"))
        poly([(168, 86), (180, 86), (168, 75)], C("#8a4050"))
        rect(172, 71, 3, 8, C("#3a2044"))
        rect(174, 71, 1, 8, stone_lit)
        # curtain walls that follow the terraces
        stone(62, 98, 26, 14)
        battlement(62, 95, 26)
        stone(150, 96, 30, 14)
        battlement(150, 93, 30)
        # slim watch turret on the far left
        stone(60, 84, 8, 28)
        cone(64, 84, 6, 72)
        # round tower on the left terrace
        drum(80, 66, 16, 46)
        rect(78, 63, 20, 3, C("#3a2044"))
        for i in range(0, 20, 4):
            rect(78 + i, 66, 2, 2, C("#22112c"))
        cone(88, 63, 12, 48)
        # square tower on the right terrace
        stone(148, 68, 12, 42)
        rect(146, 66, 16, 3, C("#3a2044"))
        cone(154, 66, 10, 54)
        # the great keep
        stone(106, 76, 32, 28)
        rect(104, 73, 36, 3, C("#3a2044"))
        for i in range(0, 36, 4):
            rect(104 + i, 76, 2, 2, C("#22112c"))
        battlement(104, 70, 36)
        stone(102, 86, 4, 18)
        stone(138, 86, 4, 18)
        # tall central tower and spire
        stone(117, 56, 12, 20)
        rect(115, 53, 16, 3, C("#3a2044"))
        cone(123, 53, 10, 44)
        rect(123, 38, 1, 6, C("#e0925a"))
        poly([(124, 38), (131, 40), (124, 42)], C("#ff7a2a"))
        # banners on the keep
        for bx in (107, 134):
            rect(bx, 78, 3, 12, C("#8e2a36"))
            rect(bx + 2, 78, 1, 12, C("#d9563a"))
            poly([(bx, 90), (bx + 3, 90), (bx + 1, 93)], C("#8e2a36"))
        # the gate, arched, with a portcullis
        rect(118, 92, 10, 12, C("#160a1e"))
        pygame.draw.circle(land, C("#160a1e"), (123, 92), 5)
        rect(117, 92, 1, 12, C("#7c403d"))
        rect(128, 92, 1, 12, C("#a45b45"))
        for gx in (120, 123, 126):
            rect(gx, 89, 1, 15, C("#5a4030"))
        rect(118, 97, 10, 1, C("#5a4030"))
        rect(118, 101, 10, 1, C("#5a4030"))
        # a winding path cut into the mountainside, from the gate down to the valley
        path = [(123, 104), (123, 107), (134, 108), (146, 111), (155, 112), (165, 117), (171, 124), (169, 132), (160, 138), (154, 142), (148, 150)]
        for (x1, y1), (x2, y2) in zip(path, path[1:]):
            pygame.draw.line(land, C("#b47a58"), (x1, y1), (x2, y2), 2)
            pygame.draw.line(land, C("#6a3d48"), (x1, y1 + 2), (x2, y2 + 2), 1)

        # dark hills, pine trees and the foreground
        hills = [(0, 192)] + [(x, int(148 + 5 * math.sin(x * 0.03) + 3 * math.sin(x * 0.11))) for x in range(0, 321, 8)] + [(320, 192)]
        poly(hills, C("#26123c"))

        def pine(x, base, h, col):
            for i in range(4):
                w = 4 + i * 3
                y0 = base - h + i * (h // 4)
                poly([(x - w, y0 + h // 3), (x + w, y0 + h // 3), (x, y0)], col)
            rect(x - 1, base - 3, 2, 3, col)

        tree = C("#170a28")
        for x, b, h in [(8, 156, 26), (22, 158, 30), (38, 155, 24), (52, 159, 28), (196, 158, 28), (212, 156, 24),
                        (226, 159, 30), (300, 160, 30), (314, 158, 26)]:
            pine(x, b, h, tree)
        poly([(0, 172), (40, 165), (90, 169), (150, 165), (210, 168), (232, 166), (232, 192), (0, 192)], C("#0e0618"))
        pine(14, 182, 46, C("#0a0412"))
        pine(38, 188, 36, C("#0a0412"))
        # the dungeon entrance carved into the rock
        poly([(232, 192), (238, 166), (250, 152), (268, 146), (288, 150), (304, 162), (312, 192)], C("#1c0e2e"))
        for (x, y) in [(244, 160), (256, 154), (274, 152), (292, 158), (244, 176), (296, 174), (300, 184), (240, 186)]:
            rect(x, y, 6, 2, C("#2c1745"))
        rect(262, 168, 16, 24, C("#07030d"))
        pygame.draw.circle(land, C("#07030d"), (270, 168), 8)
        for i, y in enumerate((178, 183, 188)):
            rect(263 + i, y, 14 - 2 * i, 1, C("#3a1d55"))
        for (x, y) in TORCHES:
            rect(x - 1, y - 2, 2, 8, C("#4a2c18"))
        self.land = pygame.transform.scale(land, (CW, CH))

        self.mist = {}
        for w in (150, 170, 140):
            m = pygame.Surface((w, 12), pygame.SRCALPHA)
            for (cx, cy, rw, rh) in ((w * 0.18, 7, 28, 3), (w * 0.42, 5, 42, 4), (w * 0.68, 7, 34, 3), (w * 0.9, 5, 22, 3)):
                pygame.draw.ellipse(m, (225, 175, 195, 55), (int(cx - rw), int(cy - rh), int(rw * 2), int(rh * 2)))
            self.mist[w] = pygame.transform.scale(m, (w * SC, 12 * SC))
        self.stars = [(rng.randint(0, W - 1), rng.randint(0, 72), rng.random() * 6.28, rng.random()) for _ in range(70)]
        self.clouds = []
        for (y, w, h, speed, x0) in CLOUDS:
            self.clouds.append((y, pygame.transform.scale(_make_cloud(w, h, rng), (w * SC, h * SC)), w, speed, x0))
        self.embers = [[rng.uniform(0, W), rng.uniform(70, H), rng.uniform(8, 22), rng.random() * 6.28, rng.random() < 0.3]
                       for _ in range(30)]
        self.birds = [[rng.uniform(0, W), rng.uniform(82, 110), rng.uniform(5, 9), rng.random() * 6.28] for _ in range(3)]

    def draw(self, surf, t):
        surf.blit(self.sky, (0, 0))
        # twinkling stars
        for (x, y, ph, br) in self.stars:
            tw = 0.5 + 0.5 * math.sin(t * (1.2 + br * 1.5) + ph)
            col = (255, 255, 255) if tw > 0.8 else (C("#c8c0e8") if tw > 0.35 else C("#7a6ab0"))
            frect(surf, x, y, 1, 1, col)
        # drifting clouds
        for (y, img, w, speed, x0) in self.clouds:
            x = ((x0 + t * speed) % (W + w * 2)) - w
            surf.blit(img, (int(x * SC), y * SC))
        surf.blit(self.land, (0, 0))
        # windows glow, some flicker
        for (x, y, spd, ph, kind) in WINDOWS:
            on = spd == 0.0 or math.sin(t * spd * 3 + ph) > -0.6
            col = C("#ffd34d") if on else C("#a2571f")
            if kind == "s":
                frect(surf, x, y, 1, 4, col)
            else:
                frect(surf, x, y + 1, 3, 3, col)
                frect(surf, x + 1, y, 1, 1, col)
                if on:
                    frect(surf, x, y + 3, 3, 1, C("#ffb040"))
        # torches on the castle walls and lanterns along the path
        for i, (x, y) in enumerate(WALL_TORCHES):
            f = math.sin(t * 12 + i * 3) > 0
            frect(surf, x, y, 1, 2, C("#ffb040") if f else C("#ff7a2a"))
            frect(surf, x, y - 1, 1, 1, C("#fff0a0") if f else C("#ffb040"))
            surf.blit(alpha_surf(8 * SC, 8 * SC, (255, 150, 50), 0.10), ((x - 3) * SC, (y - 3) * SC))
        for i, (x, y) in enumerate(LANTERNS):
            on = math.sin(t * 3 + i * 1.7) > -0.8
            frect(surf, x, y, 2, 2, C("#ffd34d") if on else C("#a2571f"))
        # chimney smoke drifting up from the hall
        for k in range(5):
            age = (t * 0.7 + k * 0.2) % 1.0
            px = 173.5 + math.sin(age * 5 + k) * 2 + age * 9
            py = 70 - age * 22
            size = 2 + int(age * 3)
            surf.blit(alpha_surf(size * SC, size * SC, (210, 170, 190), round(0.42 * (1 - age), 2)), (int(px * SC), int(py * SC)))
        # mist drifting around the base of the crag
        for (y, phase, w) in ((124, 0.0, 150), (134, 2.0, 170), (144, 4.0, 140)):
            mx = 20 + math.sin(t * 0.25 + phase) * 14
            surf.blit(self.mist[w], (int(mx * SC), y * SC))
        # gate and dungeon glow breathe
        flick = 0.5 + 0.5 * math.sin(t * 5.0) * 0.6 + 0.2 * math.sin(t * 11.3)
        surf.blit(alpha_surf(14 * SC, 13 * SC, (255, 150, 50), round(0.30 + 0.12 * flick, 2)), (116 * SC, 91 * SC))
        surf.blit(alpha_surf(20 * SC, 24 * SC, (255, 110, 30), round(0.16 + 0.08 * flick, 2)), (260 * SC, 168 * SC))
        for i, (x, y) in enumerate(TORCHES):
            f = math.sin(t * 13 + i * 2) > 0
            surf.blit(alpha_surf(30 * SC, 30 * SC, (255, 150, 50), round(0.07 + 0.03 * flick, 2)), ((x - 15) * SC, (y - 16) * SC))
            frect(surf, x - 2, y - 6, 4, 5, C("#ff8a2a"))
            frect(surf, x - 1 + (1 if f else 0), y - 7, 2, 4, C("#ffd34d"))
        # birds crossing the sky
        for b in self.birds:
            x = (b[0] + t * b[2]) % (W + 40) - 20
            up = int(t * 5 + b[3]) % 2 == 0
            cells = ((-3, -2), (-2, -1), (-1, 0), (0, 0), (1, 0), (2, -1), (3, -2)) if up else ((-3, 0), (-2, 0), (-1, -1), (0, -1), (1, -1), (2, 0), (3, 0))
            for dx, dy in cells:
                frect(surf, rnd(x) + dx, rnd(b[1]) + dy, 1, 1, C("#1a0c2a"))
        # embers rising from the keep and the dungeon
        for e in self.embers:
            y = (e[1] - t * e[2]) % (H + 20) + 0
            x = (e[0] + math.sin(t * 0.8 + e[3]) * 6) % W
            if y > H:
                continue
            col = C("#ffb347") if int(t * 6 + e[3] * 3) % 3 else C("#ff7a2a")
            frect(surf, rnd(x), rnd(y), 2 if e[4] else 1, 2 if e[4] else 1, col)



# ----------------------------------------------------------------------------
# The game
# ----------------------------------------------------------------------------
PANEL_POS = {"splash": (4, 136), "title": (4, 3)}   # where the volume sliders sit on each menu
PANEL_W, PANEL_H = 100, 28


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Emberkeep")
        try:
            pygame.display.set_icon(pygame.transform.scale(
                Sprite(SPRITE_DATA["rogue"][0], SPRITE_DATA["rogue"][1]).img, (32, 32)))
        except Exception:
            pass
        try:
            self.screen = pygame.display.set_mode((CW, CH), pygame.SCALED | pygame.RESIZABLE | pygame.NOFRAME)
        except pygame.error:
            self.screen = pygame.display.set_mode((CW, CH), pygame.NOFRAME)
        self.world = pygame.Surface((CW, CH))
        self.clock = pygame.time.Clock()
        self.sfx = Sfx()
        self.music = Music()
        self.vol_music = 0.55
        self.vol_sfx = 0.8
        self.drag = None
        self._blip_at = 0

        self.S = {}
        for name, (rows, pal) in SPRITE_DATA.items():
            self.S[name] = Sprite(rows, pal)
            self.S[name].convert()
        self.bg = build_background().convert()
        self.hub_bg = build_hub_background().convert()
        self.camp_objs = [NS(kind=k, x=tx * T + 8.0, y=ty * T + 8.0) for k, tx, ty in CAMP_OBJECTS]
        self.dummy = NS(kind="dummy", x=CAMP_DUMMY[0] * T + 8.0, y=CAMP_DUMMY[1] * T + 8.0, r=6, wobble=0.0, hits=0, show_t=0.0)
        self.fade = 0.0
        self.fade_target = 0.0
        self.fade_cb = None
        self.hub_hint = 0.0
        self.shop_open = False
        self.dev_open = False
        self.dev_invincible = False
        self.bank_coins = 0
        self.bank_emeralds = 0
        self.bank_rubies = 0
        for u in ALL_UPGRADES:
            setattr(self, "upg_" + u["id"], 0)
        self.scene = TitleScene()

        self.best = 0
        self.sel = 0
        self._load_save()
        self.apply_volumes()

        self.state = "title"
        self.paused = False
        self.confirm = ""
        self.time = 0.0
        self.over_t = 0.0
        self.banner_t = 0.0
        self.banner_text = ""
        self.shake = 0.0
        self.aim_request = None
        self.want_atk = False
        self.want_dash = False
        self.reset()
        self.state = "splash"

    # ---- saving --------------------------------------------------------
    def _load_save(self):
        for path in (SAVE_PATH, LEGACY_SAVE_PATH):
            try:
                data = json.loads(path.read_text())
                self.best = int(data.get("best", 0))
                ids = [c.id for c in CLASSES]
                if data.get("class") in ids:
                    self.sel = ids.index(data["class"])
                self.vol_music = clamp(float(data.get("music", self.vol_music)), 0.0, 1.0)
                self.vol_sfx = clamp(float(data.get("sfx", self.vol_sfx)), 0.0, 1.0)
                self.bank_coins = max(0, int(data.get("bank_coins", 0)))
                self.bank_emeralds = max(0, int(data.get("bank_emeralds", 0)))
                self.bank_rubies = max(0, int(data.get("bank_rubies", 0)))
                for u in ALL_UPGRADES:
                    lvl = int(data.get("upg_" + u["id"], 0))
                    setattr(self, "upg_" + u["id"], clamp(lvl, 0, u["max_level"]))
                break
            except Exception:
                continue

    def _write_save(self):
        try:
            data = {"best": self.best, "class": CLASSES[self.sel].id,
                    "music": round(self.vol_music, 2), "sfx": round(self.vol_sfx, 2),
                    "bank_coins": self.bank_coins, "bank_emeralds": self.bank_emeralds, "bank_rubies": self.bank_rubies}
            for u in ALL_UPGRADES:
                data["upg_" + u["id"]] = getattr(self, "upg_" + u["id"])
            SAVE_PATH.write_text(json.dumps(data))
        except Exception:
            pass

    # ---- volume --------------------------------------------------------
    def apply_volumes(self):
        self.sfx.set_volume(self.vol_sfx)
        self.music.set_volume(self.vol_music)
        self.music.set_muted(self.sfx.muted)

    def toggle_mute(self):
        self.sfx.muted = not self.sfx.muted
        self.music.set_muted(self.sfx.muted)

    def set_volume(self, idx, v):
        v = round(clamp(v, 0.0, 1.0), 2)
        if idx == 0:
            self.vol_music = v
        else:
            self.vol_sfx = v
        self.apply_volumes()

    def slider_track(self, idx):
        px, py = PANEL_POS[self.state]
        return px + 36, py + 5 + idx * 12, 40, 6

    def slider_at(self, gx, gy):
        if self.state not in PANEL_POS:
            return None
        for idx in (0, 1):
            x, y, w, h = self.slider_track(idx)
            if x - 4 <= gx <= x + w + 4 and y - 4 <= gy <= y + h + 4:
                return idx
        return None

    def drag_slider(self, idx, gx):
        x, y, w, h = self.slider_track(idx)
        self.set_volume(idx, (gx - x) / w)
        now = pygame.time.get_ticks()
        if idx == 1 and now - self._blip_at > 140:      # let the player hear the sound level
            self._blip_at = now
            self.sfx.play("select")

    def draw_volume_panel(self, scr):
        if self.state not in PANEL_POS:
            return
        px, py = PANEL_POS[self.state]
        scr.blit(alpha_surf(PANEL_W * SC, PANEL_H * SC, (10, 6, 22), 0.62), (px * SC, py * SC))
        for idx, (label, val) in enumerate((("MUSIC", self.vol_music), ("SOUND", self.vol_sfx))):
            x, y, w, h = self.slider_track(idx)
            draw_text(scr, label, px + 4, y - 0.5, C("#c9c2e8"))
            frect(scr, x - 1, y - 1, w + 2, h + 2, OUTLINE)
            frect(scr, x, y, w, h, C("#2a1d40"))
            fw = rnd(w * val)
            if fw > 0:
                frect(scr, x, y, fw, h, C("#ff9a3c"))
                frect(scr, x, y, fw, 1, C("#ffd070"))
            frect(scr, x + fw - 1, y - 2, 3, h + 4, (255, 255, 255) if self.drag == idx else C("#ffe9c0"))
            draw_text(scr, "%d" % round(val * 100), x + w + 5, y - 0.5, C("#f2c94c"))

    # ---- game flow -----------------------------------------------------
    def effective_class(self, cl):
        """A per-run copy of the class stats with bought upgrades layered on top."""
        eff = NS(**vars(cl))
        eff.hp = cl.hp + self.upg_vitality * 15
        eff.cd = max(0.12, cl.cd * (1 - 0.06 * self.upg_sharpness))
        eff.speed = cl.speed * (1 + 0.06 * self.upg_swiftness)
        eff.dash_v = cl.dash_v * (1 + 0.06 * self.upg_swiftness)
        eff.pierce = 0
        cu = CLASS_UPGRADES.get(cl.id)
        lvl = getattr(self, "upg_" + cu["id"]) if cu else 0
        if cl.id == "knight":
            eff.arc = cl.arc + 0.12 * lvl
            eff.kb = cl.kb + 25 * lvl
        elif cl.id == "rogue":
            eff.dash_cd = max(0.2, cl.dash_cd * (1 - 0.15 * lvl))
        elif cl.id == "mage":
            eff.pierce = lvl
        return eff

    def reset(self, hub=False):
        set_map("camp" if hub else "dungeon")
        cl = self.effective_class(CLASSES[self.sel])
        self.P = NS(cls=cl, max_hp=cl.hp, x=160.0, y=96.0, r=6, hp=cl.hp, hp_lag=float(cl.hp), face=0.0, flip=False,
                    inv=0.0, cd=0.0, atk_t=0.0, atk_a=0.0, dash=0.0, dash_cd=0.0, dx=1.0, dy=0.0,
                    walk=0.0, trail=[], flash=0.0, moving=False)
        if hub:
            self.P.x, self.P.y = 160.0, 150.0
            self.P.face = -math.pi / 2
        self.enemies, self.arrows, self.markers = [], [], []
        self.parts, self.pops, self.bolts = [], [], []
        self.pickups = []
        self.coins = 0
        self.emeralds = 0
        self.rubies = 0
        self.hud_flash = 0.0
        self.wave = 0
        self.score = 0
        self.kills = 0
        self.shake = 0.0
        self.wave_delay = 0.0
        self.paused = False
        self.confirm = ""
        self.run_complete = False
        if hub:
            self.dummy.wobble, self.dummy.hits, self.dummy.show_t = 0.0, 0, 0.0
        else:
            self.start_wave(1)

    def start_wave(self, n):
        self.wave = n
        count = min(3 + int(n * 1.6), 16)
        pool = ["slime"]
        if n >= 2:
            pool.append("bat")
        if n >= 3:
            pool.append("skel")
        if n >= 5:
            pool += ["skel", "bat"]
        P = self.P
        for i in range(count):
            x = y = 0
            for _ in range(60):
                tx, ty = random.randint(1, 18), random.randint(1, 10)
                x, y = tx * T + 8, ty * T + 8
                if not solid_tile(tx, ty) and math.hypot(x - P.x, y - P.y) > 80:
                    break
            self.markers.append(NS(x=x, y=y, t=0.9 + i * 0.18, type=random.choice(pool)))
        self.banner_text = "WAVE %d" % n
        self.banner_t = 1.3

    def make_enemy(self, kind, x, y):
        d = DEF[kind]
        return NS(type=kind, x=x, y=y, r=d["r"], hp=d["hp"], speed=d["speed"], t=0.0, kx=0.0, ky=0.0,
                  flash=0.0, flip=False, ph=random.random() * 6.28, cd=1.6 + random.random(),
                  aim=False, throw_t=0.0, s=random.choice((1, -1)), dead=False)

    # ---- dev/testing tools ---------------------------------------------
    DEV_ROWS = [
        ("SPAWN SLIME", "F2"), ("SPAWN BAT", "F3"), ("SPAWN SKELETON", "F4"),
        ("FULL HEAL", "F5"), ("+100/20/10 LOOT", "F6"),
        ("INVINCIBILITY", "F7"), ("+500 SCORE", "F8"), ("LEAVE DUNGEON", "F9"),
    ]

    def dev_spawn(self, kind):
        if self.state != "play":
            return
        P = self.P
        x = y = 0
        for _ in range(40):
            tx, ty = random.randint(1, 18), random.randint(1, 10)
            x, y = tx * T + 8, ty * T + 8
            if not solid_tile(tx, ty) and math.hypot(x - P.x, y - P.y) > 40:
                break
        self.enemies.append(self.make_enemy(kind, x, y))
        self.sfx.play("select")

    def dev_heal(self):
        self.P.hp = self.P.max_hp
        self.P.hp_lag = float(self.P.max_hp)
        self.hud_flash = 0.3
        self.sfx.play("clear")

    def dev_give_loot(self):
        if self.state == "play":
            self.coins += 100
            self.emeralds += 20
            self.rubies += 10
        else:
            self.bank_coins += 100
            self.bank_emeralds += 20
            self.bank_rubies += 10
            self._write_save()
        self.hud_flash = 0.3
        self.sfx.play("coin")

    def dev_toggle_invincible(self):
        self.dev_invincible = not self.dev_invincible
        self.sfx.play("select")

    def dev_add_score(self):
        self.score += 500
        self.hud_flash = 0.3
        self.sfx.play("select")

    def dev_leave_dungeon(self):
        if self.state != "play":
            return
        self.bank_coins += self.coins
        self.bank_emeralds += self.emeralds
        self.bank_rubies += self.rubies
        self._write_save()
        self.begin_fade(self.enter_hub)

    def dev_action(self, idx):
        [lambda: self.dev_spawn("slime"), lambda: self.dev_spawn("bat"), lambda: self.dev_spawn("skel"),
         self.dev_heal, self.dev_give_loot, self.dev_toggle_invincible, self.dev_add_score,
         self.dev_leave_dungeon][idx]()

    DEV_X0, DEV_Y0, DEV_W = W - 122, 22, 118

    def dev_row_rect(self, i):
        x = self.DEV_X0 + 3
        y = self.DEV_Y0 + 15 + i * 16
        return x, y, self.DEV_W - 6, 14

    def dev_row_at(self, gx, gy):
        for i in range(len(self.DEV_ROWS)):
            x, y, w, h = self.dev_row_rect(i)
            if x <= gx <= x + w and y <= gy <= y + h:
                return i
        return None

    def draw_dev_panel(self, scr):
        x0, y0, w0 = self.DEV_X0, self.DEV_Y0, self.DEV_W
        h0 = 15 + len(self.DEV_ROWS) * 16 + 4
        scr.blit(alpha_surf(w0 * SC, h0 * SC, (10, 6, 22), 0.88), (x0 * SC, y0 * SC))
        frect(scr, x0, y0, w0, 2, C("#f2c94c"))
        draw_text(scr, "DEV MODE  F1", x0 + 4, y0 + 5, C("#f2c94c"), scale=1)
        for i, (label, keyhint) in enumerate(self.DEV_ROWS):
            x, y, w, h = self.dev_row_rect(i)
            active = i == 5 and self.dev_invincible          # invincibility row shows its ON state
            frect(scr, x, y, w, h, C("#2f5a35") if active else C("#22304a"))
            draw_text(scr, label, x + 3, y + 3, (255, 255, 255), scale=1)
            draw_text(scr, "ON" if active else keyhint, x + w - 3, y + 3,
                      C("#8fe6a0") if active else C("#f2c94c"), "right", scale=1)

    def start_game(self):
        if self.state == "title":
            self.sfx.play("start")
            self.begin_fade(self.enter_hub)
        elif self.state == "over" and self.over_t <= 0:
            self.do_restart()

    def begin_fade(self, callback):
        """Fade to black, run callback, fade back in."""
        if self.fade_cb is None:
            self.fade_cb = callback
            self.fade_target = 1.0

    def enter_hub(self):
        self.reset(hub=True)
        self.state = "hub"
        self.hub_hint = 9.0

    def enter_dungeon(self):
        self.reset()
        self.state = "play"

    def shop_cards(self):
        """The 4 upgrades on offer: the 3 universal ones plus this class's own special."""
        cu = CLASS_UPGRADES.get(CLASSES[self.sel].id)
        return UPGRADES + ([cu] if cu else [])

    def buy_upgrade(self, idx):
        cards = self.shop_cards()
        if not (0 <= idx < len(cards)):
            return
        u = cards[idx]
        level = getattr(self, "upg_" + u["id"])
        if level >= u["max_level"]:
            return
        cost = upgrade_cost(u, level)
        if any(getattr(self, "bank_" + cur) < amt for cur, amt in cost.items()):
            return
        for cur, amt in cost.items():
            setattr(self, "bank_" + cur, getattr(self, "bank_" + cur) - amt)
        setattr(self, "upg_" + u["id"], level + 1)
        self.P.cls = self.effective_class(CLASSES[self.sel])   # feel the upgrade immediately
        self.P.max_hp = self.P.cls.hp
        self.P.hp = min(self.P.max_hp, self.P.hp + (15 if u["id"] == "vitality" else 0))
        self.P.hp_lag = float(self.P.hp)
        self._write_save()
        self.hud_flash = 0.3
        self.sfx.play(CUR_SFX[primary_currency(u)])

    def do_restart(self):
        self.reset()
        self.state = "play"
        self.sfx.play("start")

    def enter_menu(self):
        self.state = "title"
        self.sfx.play("select")

    def to_menu(self):
        self.state = "title"
        self.paused = False
        self.confirm = ""

    def resume(self):
        self.paused = False
        self.confirm = ""

    def press_pause(self):
        if self.state != "play":
            return
        if self.paused:
            self.resume()
        else:
            self.paused = True
            self.confirm = ""

    def press_camp(self):
        """H: back to the camp (asks first when a run is in progress)."""
        if self.state == "over":
            self.begin_fade(self.enter_hub)
        elif self.state != "play":
            return
        elif not self.paused:
            self.paused, self.confirm = True, "camp"
        elif self.confirm == "camp":
            self.begin_fade(self.enter_hub)
        else:
            self.confirm = "camp"

    def press_restart(self):
        if self.state == "hub":
            return
        if self.state == "title":
            self.start_game()
        elif self.state == "over":
            self.do_restart()
        elif not self.paused:
            self.paused, self.confirm = True, "restart"
        elif self.confirm == "restart":
            self.do_restart()
        else:
            self.confirm = "restart"

    def press_menu(self):
        if self.state == "title":
            return
        if self.state == "hub":
            self.to_menu()
        elif self.state == "over":
            self.to_menu()
        elif not self.paused:
            self.paused, self.confirm = True, "menu"
        elif self.confirm == "menu":
            self.to_menu()
        else:
            self.confirm = "menu"

    def press_atk(self, aim=None):
        if self.state not in ("play", "hub"):
            self.start_game()
            return
        if self.paused:
            self.resume()
            return
        self.want_atk = True
        self.aim_request = aim

    def press_dash(self):
        if self.state == "over":
            self.start_game()
        elif self.state in ("play", "hub") and not self.paused:
            self.want_dash = True

    def select_class(self, i):
        n = len(CLASSES)
        self.sel = i % n
        self._write_save()
        self.sfx.play("select")

    def title_tap(self, gx, gy):
        for i in range(len(CLASSES)):
            x = card_x(i)
            if x <= gx <= x + CARD_W and CARD_Y <= gy <= CARD_Y + CARD_H:
                if i == self.sel:
                    self.start_game()
                else:
                    self.select_class(i)
                return

    # ---- combat --------------------------------------------------------
    def burst(self, x, y, color, n=8):
        for _ in range(n):
            a = random.random() * 6.283
            s = 20 + random.random() * 60
            self.parts.append(NS(x=x, y=y, vx=math.cos(a) * s, vy=math.sin(a) * s, t=0.0,
                                 life=0.5 + random.random() * 0.4, c=color,
                                 s=2 if random.random() < 0.4 else 1))

    def hurt(self, sx, sy, dmg):
        P = self.P
        if self.dev_invincible or P.inv > 0 or P.dash > 0 or self.state != "play":
            return False
        P.hp = max(0, P.hp - dmg)
        self.pops.append(NS(x=P.x, y=P.y - 16, text="-%d" % dmg, t=0.0, col=C("#ff6b81")))
        P.inv = 1.1
        self.shake = 5
        P.flash = 0.15
        self.burst(P.x, P.y, C("#ff4d6d"), 10)
        self.sfx.play("hurt")
        a = math.atan2(P.y - sy, P.x - sx)
        move_ent(P, math.cos(a) * 12, math.sin(a) * 12)
        if P.hp <= 0:
            self.state = "over"
            self.over_t = 0.9
            self.shake = 8
            if self.score > self.best:
                self.best = self.score
            self._write_save()
        return True

    def hit_enemy(self, e, a):
        P = self.P
        e.hp -= 1
        e.flash = 0.12
        e.kx = math.cos(a) * P.cls.kb
        e.ky = math.sin(a) * P.cls.kb
        self.burst(e.x, e.y, BURST_COLORS[e.type], 5)
        if e.hp <= 0:
            e.dead = True
            self.kills += 1
            pts = DEF[e.type]["score"]
            self.score += pts
            self.pops.append(NS(x=e.x, y=e.y - 14, text="+%d" % pts, t=0.0))
            self.burst(e.x, e.y, (255, 255, 255), 8)
            self.spawn_drops(e)
            self.sfx.play("kill")
        else:
            self.sfx.play("hit")

    def add_pickup(self, kind, x, y, value):
        a = random.random() * 6.283
        sp = random.uniform(25, 70)
        self.pickups.append(NS(kind=kind, x=x, y=y, z=2.0, r=3, vx=math.cos(a) * sp, vy=math.sin(a) * sp,
                               vz=random.uniform(90, 150), t=0.0, life=PICKUP_LIFE, value=value,
                               ph=random.random() * 6.28))

    def spawn_drops(self, e):
        d = DEF[e.type]
        chance, lo, hi = d["coins"]
        if random.random() < chance:
            for _ in range(random.randint(lo, hi)):
                self.add_pickup("coin", e.x, e.y, GEM_VALUE["coin"])
        if random.random() < d["emerald"]:
            self.add_pickup("emerald", e.x, e.y, GEM_VALUE["emerald"])
        if random.random() < d["ruby"]:
            self.add_pickup("ruby", e.x, e.y, GEM_VALUE["ruby"])

    def collect(self, p):
        P = self.P
        self.hud_flash = 0.25
        self.score += p.value * 2
        if p.kind == "coin":
            self.coins += 1
            self.burst(p.x, p.y - 4, C("#ffd34d"), 3)
            self.sfx.play("coin")
            return
        col = GEM_COLORS[p.kind]
        if p.kind == "emerald":
            self.emeralds += 1
        else:
            self.rubies += 1
        self.burst(p.x, p.y - 4, col, 8)
        self.pops.append(NS(x=P.x, y=P.y - 18, text="+%d" % (p.value * 2), t=0.0, col=col))
        self.sfx.play(p.kind)

    def update_pickups(self, dt):
        P = self.P
        keep = []
        for p in self.pickups:
            p.t += dt
            p.life -= dt
            if p.life <= 0:
                continue
            if p.z > 0 or p.vz > 0:                    # pop out of the enemy, bounce, and come to rest
                p.vz -= 320 * dt
                p.z += p.vz * dt
                move_ent(p, p.vx * dt, p.vy * dt)
                fr = 0.5 ** (dt * 3)
                p.vx *= fr
                p.vy *= fr
                if p.z <= 0:
                    p.z = 0.0
                    if p.vz < -50:
                        p.vz = -p.vz * 0.4
                    else:
                        p.vz = 0.0
                        p.vx = p.vy = 0.0
            d = math.hypot(P.x - p.x, P.y - p.y)
            if p.t > 0.3 and d < MAGNET_RANGE:          # the magnet pulls loot toward the player
                sp = 80 + (MAGNET_RANGE - d) * 6
                p.x += (P.x - p.x) / (d or 1) * sp * dt
                p.y += (P.y - p.y) / (d or 1) * sp * dt
            if p.t > 0.25 and d < P.r + 4:
                self.collect(p)
                continue
            keep.append(p)
        self.pickups = keep

    def hit_dummy(self, a):
        d = self.dummy
        d.wobble = 1.0
        d.hits += 1
        d.show_t = 2.5
        self.burst(d.x, d.y - 10, C("#e8c860"), 6)
        self.sfx.play("hit")

    def update_hub(self, dt):
        P, d = self.P, self.dummy
        d.wobble = max(0.0, d.wobble - dt * 2.2)
        d.show_t = max(0.0, d.show_t - dt)
        self.hub_hint = max(0.0, self.hub_hint - dt)
        if random.random() < dt * 9:                       # sparks drift up from the campfire
            fx, fy = CAMP_FIRE
            self.parts.append(NS(x=fx + random.uniform(-4, 4), y=fy - 6, vx=random.uniform(-8, 8),
                                 vy=random.uniform(-40, -22), t=0.0, life=random.uniform(0.6, 1.2),
                                 c=C("#ffb347") if random.random() < 0.6 else C("#ff7a2a"), s=1))
        if self.fade_cb is None and P.y < 24 and 142 < P.x < 178:   # walking into the gate starts the run
            self.sfx.play("start")
            self.begin_fade(self.enter_dungeon)

    def face_toward(self, a):
        P = self.P
        P.face = a
        if math.cos(a) > 0.1:
            P.flip = False
        elif math.cos(a) < -0.1:
            P.flip = True

    def do_slash(self, aim):
        P = self.P
        if aim is not None:
            a = aim
        else:
            a = P.face
            nearest, bd = None, 40
            for e in self.enemies:
                d = math.hypot(e.x - P.x, e.y - P.y)
                if d < bd:
                    bd, nearest = d, e
            if nearest:
                a = math.atan2(nearest.y - P.y, nearest.x - P.x)
        self.face_toward(a)
        P.atk_t = 0.2
        P.atk_a = a
        P.cd = P.cls.cd
        R, arc = P.cls.reach, P.cls.arc
        for e in self.enemies:
            dx, dy = e.x - P.x, e.y - P.y
            d = math.hypot(dx, dy)
            if d <= R + e.r and (abs(ang_diff(math.atan2(dy, dx), a)) < arc or d < 10 + e.r):
                self.hit_enemy(e, a)
        self.enemies = [e for e in self.enemies if not e.dead]
        if self.state == "hub":
            dm = self.dummy
            ddx, ddy = dm.x - P.x, dm.y - P.y
            dd = math.hypot(ddx, ddy)
            if dd <= R + dm.r and (abs(ang_diff(math.atan2(ddy, ddx), a)) < arc or dd < 10 + dm.r):
                self.hit_dummy(a)
        keep = []
        for ar in self.arrows:
            dx, dy = ar.x - P.x, ar.y - P.y
            d = math.hypot(dx, dy)
            if d <= R and abs(ang_diff(math.atan2(dy, dx), a)) < arc + 0.15:
                self.burst(ar.x, ar.y, C("#e8e2cf"), 4)
            else:
                keep.append(ar)
        self.arrows = keep
        self.sfx.play("slash")

    def fire_bolt(self, aim):
        P = self.P
        if aim is not None:
            a = aim
        else:
            a = P.face
            nearest, bd = None, 180
            for e in self.enemies:
                d = math.hypot(e.x - P.x, e.y - P.y)
                if d < bd:
                    bd, nearest = d, e
            if nearest:
                a = math.atan2(nearest.y - P.y, nearest.x - P.x)
        self.face_toward(a)
        P.atk_t = 0.12
        P.atk_a = a
        P.cd = P.cls.cd
        ox, oy = P.x + math.cos(a) * 9, P.y + math.sin(a) * 9
        self.bolts.append(NS(x=ox, y=oy, vx=math.cos(a) * 230, vy=math.sin(a) * 230, life=1.1, a=a, pierce=P.cls.pierce))
        self.burst(ox, oy, C("#8fc4ff"), 4)
        self.sfx.play("bolt")

    # ---- update --------------------------------------------------------
    def update_enemy(self, e, dt):
        P = self.P
        e.t += dt
        if e.kx or e.ky:
            move_ent(e, e.kx * dt, e.ky * dt)
            dm = 0.02 ** dt
            e.kx *= dm
            e.ky *= dm
            if abs(e.kx) + abs(e.ky) < 4:
                e.kx = e.ky = 0
        dx, dy = P.x - e.x, P.y - e.y
        dist = math.hypot(dx, dy) or 1
        ux, uy = dx / dist, dy / dist
        if abs(ux) > 0.15:
            e.flip = ux < 0
        if e.type == "slime":
            hop = max(0.0, math.sin(e.t * 5)) * 1.6
            move_ent(e, ux * e.speed * hop * dt, uy * e.speed * hop * dt)
        elif e.type == "bat":
            w = math.sin(e.t * 6 + e.ph) * 0.9
            move_ent(e, (ux - uy * w) * e.speed * dt, (uy + ux * w) * e.speed * dt)
        else:
            mv = 1 if dist > 110 else (-1 if dist < 70 else 0)
            move_ent(e, (ux * mv - uy * e.s * 0.5) * e.speed * dt, (uy * mv + ux * e.s * 0.5) * e.speed * dt)
            e.cd -= dt
            if e.cd < 0.55:
                e.aim = True
            if e.cd <= 0:
                side = -1 if e.flip else 1
                hx, hy = e.x + side * 9, e.y - 2  # the hand releases the arrow here
                if solid_tile(int(hx // T), int(hy // T)):
                    hx, hy = e.x, e.y - 3
                d = math.hypot(P.x - hx, P.y - hy) or 1
                self.arrows.append(NS(x=hx, y=hy, vx=(P.x - hx) / d * 70, vy=(P.y - hy) / d * 70, r=2, life=5.0))
                e.cd = 2.4 + random.random() * 0.6
                e.aim = False
                e.throw_t = 0.3
            if e.throw_t > 0:
                e.throw_t -= dt

    def update(self, dt, keys):
        # screen fades (class select -> camp -> dungeon)
        if self.fade_cb is not None:                  # fading to black to run a scene change
            self.fade = min(1.0, self.fade + dt * 3.0)
            if self.fade >= 1.0:                       # reached black even if it started there already
                callback, self.fade_cb = self.fade_cb, None
                callback()
                self.fade_target = 0.0
        elif self.fade > self.fade_target:             # fading back in afterward
            self.fade = max(0.0, self.fade - dt * 3.0)
        if self.paused and self.state == "play":
            return
        if self.shop_open:
            return
        self.time += dt
        self.shake = max(0.0, self.shake - 30 * dt)
        self.hud_flash = max(0.0, self.hud_flash - dt)
        if self.state in ("title", "splash"):
            return
        if self.state == "over":
            self.over_t -= dt
        for p in self.pops:
            p.t += dt
            p.y -= 10 * dt
        self.pops = [p for p in self.pops if p.t < 1.1]
        self.banner_t -= dt

        P = self.P
        if P.hp_lag > P.hp:
            P.hp_lag = max(float(P.hp), P.hp_lag - 45 * dt)
        else:
            P.hp_lag = float(P.hp)
        if self.state in ("play", "hub"):
            mx = (1 if keys[pygame.K_d] or keys[pygame.K_RIGHT] else 0) - (1 if keys[pygame.K_a] or keys[pygame.K_LEFT] else 0)
            my = (1 if keys[pygame.K_s] or keys[pygame.K_DOWN] else 0) - (1 if keys[pygame.K_w] or keys[pygame.K_UP] else 0)
            m = math.hypot(mx, my)
            if m > 1:
                mx, my, m = mx / m, my / m, 1.0
            if self.fade_cb is not None:               # no control while the screen fades out
                mx = my = m = 0.0
                self.want_atk = self.want_dash = False
            moving = m > 0.2
            P.moving = moving
            P.inv -= dt
            P.cd -= dt
            P.dash_cd -= dt
            P.flash -= dt
            if P.atk_t > 0:
                P.atk_t -= dt

            if self.want_dash and P.dash_cd <= 0 and P.dash <= 0:
                if moving:
                    P.dx, P.dy = mx / m, my / m
                else:
                    P.dx, P.dy = math.cos(P.face), math.sin(P.face)
                P.dash = 0.14
                P.dash_cd = P.cls.dash_cd
                self.sfx.play("dash")
            if P.dash > 0:
                P.dash -= dt
                move_ent(P, P.dx * P.cls.dash_v * dt, P.dy * P.cls.dash_v * dt)
                P.trail.append(NS(x=P.x, y=P.y, f=P.flip, t=0.16))
            elif moving:
                move_ent(P, mx * P.cls.speed * dt, my * P.cls.speed * dt)
                P.face = math.atan2(my, mx)
                if abs(mx) > 0.2:
                    P.flip = mx < 0
                P.walk += dt * 10
            if self.want_atk and P.cd <= 0 and P.atk_t <= 0:
                if P.cls.ranged:
                    self.fire_bolt(self.aim_request)
                else:
                    self.do_slash(self.aim_request)
            self.want_atk = self.want_dash = False
            self.aim_request = None
            for t in P.trail:
                t.t -= dt
            P.trail = [t for t in P.trail if t.t > 0]

            for mk in self.markers:
                mk.t -= dt
                if mk.t <= 0:
                    self.enemies.append(self.make_enemy(mk.type, mk.x, mk.y))
                    self.burst(mk.x, mk.y, C("#ff5a7a"), 6)
            self.markers = [mk for mk in self.markers if mk.t > 0]

            for e in self.enemies:
                self.update_enemy(e, dt)
                e.flash -= dt
            n = len(self.enemies)
            for i in range(n):
                for j in range(i + 1, n):
                    a, b = self.enemies[i], self.enemies[j]
                    dx, dy = a.x - b.x, a.y - b.y
                    d = math.hypot(dx, dy)
                    mn = a.r + b.r
                    if 0.01 < d < mn:
                        push = (mn - d) * 0.5 * min(1.0, dt * 12)
                        move_ent(a, dx / d * push, dy / d * push)
                        move_ent(b, -dx / d * push, -dy / d * push)

            for b in self.bolts:
                b.x += b.vx * dt
                b.y += b.vy * dt
                b.life -= dt
                if random.random() < 0.8:
                    self.parts.append(NS(x=b.x + (random.random() - .5) * 6, y=b.y + (random.random() - .5) * 6,
                                         vx=(random.random() - .5) * 24, vy=(random.random() - .5) * 24, t=0.0,
                                         life=0.25 + random.random() * 0.25,
                                         c=C("#8fc4ff") if random.random() < 0.5 else (255, 255, 255), s=1))
                if self.state == "hub" and math.hypot(self.dummy.x - b.x, self.dummy.y - b.y) < self.dummy.r + 4:
                    self.hit_dummy(b.a)
                    b.life = 0
                    continue
                if solid_tile(int(b.x // T), int(b.y // T)):
                    b.life = 0
                    self.burst(b.x, b.y, C("#8fc4ff"), 4)
                    continue
                used = False
                for e in self.enemies:
                    if not e.dead and math.hypot(e.x - b.x, e.y - b.y) < e.r + 3:
                        self.hit_enemy(e, b.a)
                        if b.pierce > 0:
                            b.pierce -= 1                # punches through instead of stopping
                        else:
                            b.life = 0
                        used = True
                        break
                if used:
                    continue
                for ar in self.arrows:
                    if ar.life > 0 and math.hypot(ar.x - b.x, ar.y - b.y) < 6:
                        ar.life = 0
                        b.life = 0
                        self.burst(ar.x, ar.y, C("#e8e2cf"), 4)
                        break
            self.bolts = [b for b in self.bolts if b.life > 0]
            self.enemies = [e for e in self.enemies if not e.dead]
            self.arrows = [a for a in self.arrows if a.life > 0]

            for ar in self.arrows:
                ar.x += ar.vx * dt
                ar.y += ar.vy * dt
                ar.life -= dt
                if solid_tile(int(ar.x // T), int(ar.y // T)):
                    ar.life = 0
                elif math.hypot(ar.x - P.x, ar.y - P.y) < ar.r + P.r:
                    if self.hurt(ar.x - ar.vx, ar.y - ar.vy, ARROW_DMG):
                        ar.life = 0
            self.arrows = [a for a in self.arrows if a.life > 0]
            for e in self.enemies:
                touch = DEF[e.type]["dmg"]
                if touch and e.t > 0.4 and math.hypot(e.x - P.x, e.y - P.y) < e.r + P.r - 1:
                    self.hurt(e.x, e.y, touch)

            if self.state == "play":
                self.update_pickups(dt)
            if self.state == "play":
                if self.wave_delay > 0:
                    self.wave_delay -= dt
                    if self.wave_delay <= 0:
                        if self.wave >= WAVE_CAP:
                            self.begin_fade(self.enter_hub)
                        else:
                            self.start_wave(self.wave + 1)
                elif not self.enemies and not self.markers:
                    heal = WAVE_HEAL
                    P.hp = min(P.max_hp, P.hp + heal)
                    self.pops.append(NS(x=P.x, y=P.y - 16, text="+%d HP" % heal, t=0.0, col=C("#4fd08a")))
                    self.score += self.wave * 20
                    if self.wave >= WAVE_CAP:
                        if not self.run_complete:
                            self.run_complete = True
                            self.wave_delay = 3.0
                            self.bank_coins += self.coins
                            self.bank_emeralds += self.emeralds
                            self.bank_rubies += self.rubies
                            self._write_save()
                            self.banner_text = "DUNGEON CLEARED"
                            self.banner_t = 2.6
                            self.sfx.play("clear")
                    else:
                        self.wave_delay = 1.8
                        self.banner_text = "WAVE %d CLEARED" % self.wave
                        self.banner_t = 1.8
                        self.sfx.play("clear")
            if self.state == "hub":
                self.update_hub(dt)

        for p in self.parts:
            p.t += dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            dm = 0.08 ** dt
            p.vx *= dm
            p.vy *= dm
        self.parts = [p for p in self.parts if p.t < p.life]

    # ---- drawing -------------------------------------------------------
    def crect(self, surf, x, y, w, h, color):
        """Rectangle on the chunky grid (background pixels)."""
        surf.fill(color, (x * 4, y * 4, w * 4, h * 4))

    def draw_torch(self, surf, cx, cy):
        f = (math.sin(self.time * 13 + cx) + math.sin(self.time * 7.3)) * 0.5
        surf.blit(alpha_surf(22 * 4, 22 * 4, (255, 170, 60), 0.05), ((cx - 11) * 4, (cy - 7) * 4))
        surf.blit(alpha_surf(12 * 4, 12 * 4, (255, 170, 60), 0.08), ((cx - 6) * 4, (cy - 3) * 4))
        self.crect(surf, cx - 1, cy + 1, 2, 3, C("#3b2a1c"))
        self.crect(surf, cx - 1, cy - 2, 2, 3, C("#ff8a2a"))
        self.crect(surf, cx - (1 if f > 0 else 0), cy - 1, 1, 2, C("#ffd34d"))

    def shadow(self, surf, x, y, w):
        s = alpha_surf(w * SC, SC, (0, 0, 0), 0.30)
        surf.blit(s, (rnd(x - w / 2) * SC, rnd(y) * SC))
        s2 = alpha_surf((w - 2) * SC, SC, (0, 0, 0), 0.30)
        surf.blit(s2, (rnd(x - w / 2 + 1) * SC, rnd(y - 1) * SC))

    def draw_enemy(self, surf, e):
        S = self.S
        wf = e.flash > 0
        if e.type == "slime":
            # one hop per cycle: crouch, stretch in the air, then rest
            sn = math.sin(e.t * 5)
            hop = max(0.0, sn)
            frame = "slime_stretch" if sn > 0.5 else ("slime_crouch" if sn < -0.55 else "slime")
            self.shadow(surf, e.x, e.y + e.r + 2, int(16 - hop * 4))
            spr(surf, S[frame], e.x, e.y + e.r + 2 - hop * 4, False, wf)
        elif e.type == "bat":
            self.shadow(surf, e.x, e.y + e.r + 3, 12)
            spr(surf, S["bat1"] if int(e.t * 10) % 2 else S["bat0"], e.x, e.y + 2, e.flip, wf)
        else:
            # throw: wind up (arm bent, then raised), release, follow through; otherwise a walk cycle
            lift = 0
            if e.throw_t > 0:
                frame = "skel_throw" if e.throw_t > 0.15 else "skel_follow"
            elif e.aim:
                frame = "skel_windup2" if e.cd < 0.25 else "skel_windup1"
            else:
                step = int(e.t * 8) % 4
                frame = ("skel_a", "skel", "skel_b", "skel")[step]
                lift = 1 if step % 2 == 1 else 0
            by = e.y + e.r + 3 - lift
            self.shadow(surf, e.x, e.y + e.r + 3, 15)
            spr(surf, S[frame], e.x, by, e.flip, wf)
            if e.aim:
                col = C("#ff5a7a")
                frect(surf, rnd(e.x) - 1, rnd(by - S["skel"].h) - 9, 2, 5, col)
                frect(surf, rnd(e.x) - 1, rnd(by - S["skel"].h) - 3, 2, 2, col)

    def player_frame(self):
        """Which animation frame the player is in right now."""
        P = self.P
        if P.flash > 0:
            return "hurt"
        if P.dash > 0:
            return "dash"
        if P.atk_t > 0:
            if P.cls.ranged:  # thrust the staff forward, then let it glow
                return "attack2" if P.atk_t > 0.05 else "attack1"
            return "attack2" if P.atk_t <= 0.1 else "attack1"  # sword: raised, then swung
        if P.moving:
            return ("walk_a", "idle0", "walk_b", "idle0")[int(P.walk) % 4]
        return "idle1" if int(self.time * 2) % 2 else "idle0"  # slow breathing

    def draw_player(self, surf):
        P = self.P
        if self.state == "play" and P.inv > 0 and int(P.inv * 24) % 2 == 0:
            return
        bob = 1 if (P.moving and int(P.walk) % 2) else 0
        self.shadow(surf, P.x, P.y + P.r + 3, 15)
        frame = "%s_%s" % (P.cls.id, self.player_frame())
        spr(surf, self.S[frame], P.x, P.y + P.r + 3 - bob, P.flip, P.flash > 0)

    def draw_pickup(self, surf, p):
        if p.life < 3.0 and int(p.life * 8) % 2 == 0:
            return                                       # blinks before it vanishes
        lift = p.z + (0.0 if p.z > 0 else 1.5 * abs(math.sin(self.time * 4 + p.ph)))
        self.shadow(surf, p.x, p.y + 2, max(4, int(8 - lift * 0.3)))
        if p.kind == "coin":
            name, flip = (("coin_a", False), ("coin_b", False), ("coin_c", False), ("coin_b", True))[int(self.time * 9 + p.ph * 3) % 4]
            spr(surf, self.S[name], p.x, p.y + 2 - lift, flip)
            return
        spr(surf, self.S[p.kind], p.x, p.y + 2 - lift)
        if int(self.time * 5 + p.ph * 2) % 7 == 0:       # a glint of light
            gx, gy = rnd(p.x) + 3, rnd(p.y + 2 - lift) - 8
            frect(surf, gx, gy - 1, 1, 3, (255, 255, 255))
            frect(surf, gx - 1, gy, 3, 1, (255, 255, 255))

    def draw_arrow(self, surf, ar):
        sp = math.hypot(ar.vx, ar.vy) or 1
        ux, uy = ar.vx / sp, ar.vy / sp
        nx, ny = -uy, ux
        for outline in (True, False):
            for d, w, col in ARROW_PX:
                px = rnd(ar.x - ux * d + nx * w)
                py = rnd(ar.y - uy * d + ny * w)
                if outline:
                    frect(surf, px - 1, py - 1, 3, 3, OUTLINE)
                else:
                    frect(surf, px, py, 1, 1, col)

    def draw_hub_backdrop(self, surf):
        t = self.time
        surf.blit(self.hub_bg, (0, 0))
        flick = 0.5 + 0.3 * math.sin(t * 9) + 0.2 * math.sin(t * 17.3)
        # the dungeon gate glows and breathes
        surf.blit(alpha_surf(32 * SC, 26 * SC, (255, 130, 40), round(0.30 + 0.10 * flick, 2)), (144 * SC, 6 * SC))
        surf.blit(alpha_surf(32 * SC, 10 * SC, (255, 190, 90), round(0.22 + 0.08 * flick, 2)), (144 * SC, 22 * SC))
        surf.blit(alpha_surf(56 * SC, 26 * SC, (255, 140, 50), round(0.07 + 0.03 * flick, 2)), (132 * SC, 32 * SC))
        fx, fy = CAMP_FIRE                                  # campfire light on the cobbles
        surf.blit(alpha_surf(96 * SC, 96 * SC, (255, 150, 50), round(0.06 + 0.03 * flick, 2)), (int((fx - 48) * SC), int((fy - 52) * SC)))
        surf.blit(alpha_surf(48 * SC, 48 * SC, (255, 170, 70), round(0.10 + 0.04 * flick, 2)), (int((fx - 24) * SC), int((fy - 32) * SC)))

    def draw_camp_obj(self, surf, o):
        S, t = self.S, self.time
        if o.kind == "dummy":
            self.shadow(surf, o.x, o.y + 9, 12)
            spr(surf, S["dummy"], o.x + math.sin(t * 30) * 3 * o.wobble, o.y + 9)
        elif o.kind == "firepit":
            spr(surf, S["firepit"], o.x, o.y + 7)
            spr(surf, S[("fire_a", "fire_b", "fire_c")[int(t * 8) % 3]], o.x, o.y + 3)
        elif o.kind == "brazier":
            self.shadow(surf, o.x, o.y + 8, 12)
            spr(surf, S["brazier"], o.x, o.y + 8)
            spr(surf, S[("fire_b", "fire_c", "fire_a")[int(t * 8 + o.x) % 3]], o.x, o.y - 1)
            surf.blit(alpha_surf(28 * SC, 28 * SC, (255, 150, 50), 0.07), (int((o.x - 14) * SC), int((o.y - 16) * SC)))
        elif o.kind == "shop":
            self.shadow(surf, o.x, o.y + 9, 18)
            spr(surf, S["shop"], o.x, o.y + 9)
            bob = math.sin(t * 3) * 1.5
            spr(surf, S["coin_a"], o.x, o.y - 14 + bob)
        else:
            self.shadow(surf, o.x, o.y + 8, 16 if o.kind == "well" else 12)
            spr(surf, S[o.kind], o.x, o.y + 8)

    def draw_lock(self, scr, cx, cy, col):
        frect(scr, cx - 1, cy - 3, 3, 1, col)
        frect(scr, cx - 2, cy - 2, 1, 2, col)
        frect(scr, cx + 1, cy - 2, 1, 2, col)
        frect(scr, cx - 2, cy, 5, 4, col)

    def stall_rect(self):
        return 24, 64, 32, 44          # clickable area around the shop stall (world units)

    def click_on_stall(self, gx, gy):
        x, y, w, h = self.stall_rect()
        return x <= gx <= x + w and y <= gy <= y + h

    def near_shop(self):
        hx, hy = CAMP_SHOP
        return math.hypot(self.P.x - hx, self.P.y - hy) < 40

    def open_shop(self):
        if self.state == "hub" and not self.shop_open and not self.paused:
            self.shop_open = True
            self.sfx.play("select")

    def close_shop(self):
        self.shop_open = False

    def draw_upgrade_icon(self, surf, name, cx, cy, col):
        cx, cy = rnd(cx), rnd(cy)
        if name == "heart":
            spr(surf, self.S["heart"], cx, cy + 4)
            return
        if name == "bolt":
            frect(surf, cx - 1, cy - 7, 4, 2, col)
            frect(surf, cx - 3, cy - 4, 4, 2, col)
            frect(surf, cx - 1, cy - 1, 4, 2, col)
            frect(surf, cx - 3, cy + 2, 4, 2, col)
        elif name == "boot":
            frect(surf, cx - 3, cy - 7, 4, 5, col)
            frect(surf, cx - 3, cy - 2, 2, 4, col)
            frect(surf, cx - 3, cy + 1, 8, 3, col)
        elif name == "shield":
            frect(surf, cx - 5, cy - 6, 10, 6, col)
            frect(surf, cx - 4, cy, 8, 3, col)
            frect(surf, cx - 2, cy + 3, 4, 2, col)
        elif name == "dash":
            frect(surf, cx - 7, cy - 4, 4, 2, col)
            frect(surf, cx - 4, cy - 1, 4, 2, col)
            frect(surf, cx - 1, cy + 2, 4, 2, col)
        elif name == "star":
            frect(surf, cx - 1, cy - 6, 2, 12, col)
            frect(surf, cx - 6, cy - 1, 12, 2, col)

    def shop_card_rect(self, i):
        n = len(self.shop_cards())
        cw, ch, gap = 64, 110, 10
        total = n * cw + (n - 1) * gap
        x0 = (W - total) / 2
        y0 = 50
        return x0 + i * (cw + gap), y0, cw, ch

    def shop_card_at(self, gx, gy):
        for i in range(len(self.shop_cards())):
            x, y, w, h = self.shop_card_rect(i)
            if x <= gx <= x + w and y <= gy <= y + h:
                return i
        return None

    def draw_shop_screen(self, scr):
        cards = self.shop_cards()
        scr.fill(C("#140b22"))
        for i in range(0, H, 8):
            frect(scr, 0, i, W, 1, C("#1c1230"))
        draw_text(scr, "SHOPKEEPER", W / 2, 8, C("#f2c94c"), "center", 3)
        draw_text(scr, "SPEND YOUR BANKED LOOT", W / 2, 24, C("#c9c2e8"), "center")
        for ci, cur in enumerate(("coins", "emeralds", "rubies")):
            ix = W / 2 - 46 + ci * 46
            icon = {"coins": "coin_a", "emeralds": "emerald", "rubies": "ruby"}[cur]
            spr(scr, self.S[icon], ix - 4, 40)
            draw_text(scr, str(getattr(self, "bank_" + cur)), ix + 5, 32, CUR_COLOR[cur])
        for i, u in enumerate(cards):
            x, y, w, h = self.shop_card_rect(i)
            cx = x + w / 2
            level = getattr(self, "upg_" + u["id"])
            maxed = level >= u["max_level"]
            cost = None if maxed else upgrade_cost(u, level)
            afford = (not maxed) and all(getattr(self, "bank_" + cur) >= amt for cur, amt in cost.items())
            prim = CUR_COLOR[primary_currency(u)]
            border = C("#4a6a9a") if afford else (C("#5a4a2a") if maxed else C("#3a3560"))
            frect(scr, x, y, w, h, C("#22304a") if afford else C("#1a1530"))
            frect(scr, x, y, w, 2, border)
            draw_text(scr, str(i + 1), x + 4, y + 3, C("#6b6480"))
            self.draw_upgrade_icon(scr, u["icon"], cx, y + 24, prim)
            draw_text(scr, u["label"], cx, y + 40, (255, 255, 255), "center")
            for li, line in enumerate(u["effect"].split("\n")):
                draw_text(scr, line, cx, y + 52 + li * 8, C("#9a93bd"), "center", 1)
            for p in range(u["max_level"]):
                pw = (w - 8) / u["max_level"]
                pc = prim if p < level else C("#3a3560")
                frect(scr, x + 4 + p * pw, y + 74, pw - 1, 3, pc)
            if maxed:
                draw_text(scr, "MAX", cx, y + 84, C("#f2c94c"), "center")
            else:
                items = list(cost.items())
                offs = [0] if len(items) == 1 else [-15, 15]
                for (cur, amt), off in zip(items, offs):
                    col = CUR_COLOR[cur] if afford else C("#6b6480")
                    spr(scr, self.S[CUR_ICON[cur]], cx + off - 6, y + 89)
                    draw_text(scr, str(amt), cx + off + 3, y + 82, col)
            draw_text(scr, "PRESS %d" % (i + 1), cx, y + 98, C("#6b6480") if not afford else (255, 255, 255), "center")
        draw_text(scr, "ESC OR CLICK OUTSIDE TO CLOSE", W / 2, H - 10, C("#8d86b0"), "center")

    def draw_hub_overlay(self, scr):
        P, d = self.P, self.dummy
        if self.near_shop() and not self.shop_open and int(self.time * 2) % 2 == 0:
            hx, hy = CAMP_SHOP
            draw_text(scr, "CLICK STALL TO SHOP", clamp(hx, 62, W - 62), hy - 46, (255, 255, 255), "center")
        sx, sy = CAMP_SIGN
        if math.hypot(P.x - sx, P.y - sy) < 34:            # read the signpost
            scr.blit(alpha_surf(96 * SC, 50 * SC, (10, 6, 22), 0.82), (int((sx - 48) * SC), int((sy - 62) * SC)))
            for i, (line, col) in enumerate((("CONTROLS", "#f2c94c"), ("WASD  MOVE", "#ffffff"), ("SPACE  ATTACK", "#ffffff"),
                                              ("SHIFT  DASH", "#ffffff"), ("P  PAUSE", "#c9c2e8"))):
                draw_text(scr, line, sx, sy - 58 + i * 9, C(col), "center")
        if d.show_t > 0:
            draw_text(scr, "HITS %d" % d.hits, d.x, d.y - 28, C("#ffd34d"), "center")
        elif d.hits == 0 and math.hypot(P.x - d.x, P.y - d.y) < 46 and int(self.time * 2) % 2 == 0:
            draw_text(scr, "HIT ME", d.x, d.y - 28, (255, 255, 255), "center")
        if P.y < 60 and abs(P.x - 160) < 44:
            draw_text(scr, "WALK IN TO DESCEND", W / 2, 44, C("#ffb060"), "center")
        if self.hub_hint > 0 and self.fade_cb is None:
            draw_text(scr, "WALK THROUGH THE GATE TO BEGIN", W / 2, 160, (255, 255, 255), "center")

    def draw_world(self):
        surf = self.world
        hub = self.state in ("hub", "title")   # class select previews the camp, not the dungeon
        if hub:
            self.draw_hub_backdrop(surf)
        else:
            surf.blit(self.bg, (0, 0))
            self.draw_torch(surf, 64, 4)
            self.draw_torch(surf, 96, 4)
        if self.state == "title":
            return
        P = self.P
        S = self.S

        for mk in self.markers:
            col = C("#ff5a7a") if int(self.time * 6) % 2 == 0 else C("#a63a52")
            x, y = rnd(mk.x), rnd(mk.y)
            for i in range(-4, 5):
                frect(surf, x + i, y + i, 2, 2, col)
                frect(surf, x + i, y - i, 2, 2, col)
        for t in P.trail:
            spr(surf, S[P.cls.id + "_dash"], t.x, t.y + P.r + 3, t.f, True, t.t / 0.16 * 0.45)
        for p in self.pickups:
            self.draw_pickup(surf, p)
        extra = (self.camp_objs + [self.dummy]) if hub else []
        ents = sorted(self.enemies + extra + [NS(is_p=True, y=P.y)], key=lambda e: e.y)
        for e in ents:
            if getattr(e, "is_p", False):
                self.draw_player(surf)
            elif getattr(e, "kind", None) is not None:
                self.draw_camp_obj(surf, e)
            else:
                self.draw_enemy(surf, e)
        for ar in self.arrows:
            self.draw_arrow(surf, ar)
        for b in self.bolts:
            x, y = rnd(b.x), rnd(b.y)
            frect(surf, x - 5, y - 2, 10, 4, OUTLINE)
            frect(surf, x - 2, y - 5, 4, 10, OUTLINE)
            frect(surf, x - 4, y - 1, 8, 2, C("#8fc4ff"))
            frect(surf, x - 1, y - 4, 2, 8, C("#8fc4ff"))
            if int(self.time * 16) % 2:
                for ox, oy in ((-2, -2), (1, -2), (-2, 1), (1, 1)):
                    frect(surf, x + ox, y + oy, 1, 1, C("#bfe6ff"))
            frect(surf, x - 1, y - 1, 2, 2, (255, 255, 255))
        if P.atk_t > 0 and not P.cls.ranged:
            p = 1 - P.atk_t / 0.2
            n = int(30 * min(1, p * 1.6))
            fade = p * 0.7
            reach, arc = P.cls.reach, P.cls.arc
            for k in range(n + 1):
                an = P.atk_a - arc + 2 * arc * (k / 30)
                for rr in (reach - 7, reach - 3):
                    base = (255, 255, 255) if rr == reach - 7 else C("#8fc4ff")
                    col = lerp_color(base, FLOOR_TINT, fade)
                    frect(surf, rnd(P.x + math.cos(an) * rr) - 1, rnd(P.y + math.sin(an) * rr) - 1, 2, 2, col)
        for p in self.parts:
            col = lerp_color(p.c, FLOOR_TINT, p.t / p.life)
            frect(surf, rnd(p.x), rnd(p.y), p.s, p.s, col)
        for p in self.pops:
            draw_text(surf, p.text, clamp(rnd(p.x), 30, W - 30), rnd(p.y), getattr(p, "col", (255, 255, 255)), "center")

    def draw_splash(self, scr):
        self.scene.draw(scr, self.time)
        draw_big_title(scr, "EMBERKEEP", W / 2, 6, 6)
        draw_text(scr, "DUNGEONS BENEATH THE MOUNTAIN", W / 2, 31, C("#ffd9b8"), "center")
        if int(self.time * 2) % 2 == 0:
            draw_text(scr, "PRESS SPACE OR CLICK", W / 2, 168, (255, 255, 255), "center")
        draw_text(scr, "ESC: QUIT", 6, 182, C("#8d86b0"))
        if self.best > 0:
            draw_text(scr, "BEST %d" % self.best, 228, 182, C("#f2c94c"), "right")
        self.draw_volume_panel(scr)

    def draw(self):
        if self.state == "splash":
            self.draw_splash(self.screen)
            if self.dev_open:
                self.draw_dev_panel(self.screen)
            return
        if self.state == "hub" and self.shop_open:
            self.draw_shop_screen(self.screen)
            if self.dev_open:
                self.draw_dev_panel(self.screen)
            return
        self.draw_world()
        scr = self.screen
        scr.fill((18, 16, 29))
        ox = oy = 0
        if self.shake > 0:
            ox = rnd((random.random() - .5) * self.shake * 0.5) * 4
            oy = rnd((random.random() - .5) * self.shake * 0.5) * 4
        scr.blit(self.world, (ox, oy))

        if self.state != "title":
            self.draw_hud(scr)
        if self.state == "hub":
            self.draw_hub_overlay(scr)
        if self.state == "play" and not self.paused and self.banner_t > 0:
            draw_text(scr, self.banner_text, W / 2, 86, C("#f2c94c"), "center")
        if self.state == "title":
            self.draw_title(scr)
        if self.state == "over":
            self.draw_over(scr)
        if self.state == "play" and self.paused:
            self.draw_pause(scr)
        if self.fade > 0:
            scr.blit(alpha_surf(CW, CH, (0, 0, 0), round(self.fade * 20) / 20), (0, 0))
        if self.dev_open:
            self.draw_dev_panel(scr)

    def draw_health_bar(self, scr):
        P = self.P
        x, y, w, h = 6, 3, 92, 10
        frect(scr, x - 1, y - 1, w + 2, h + 2, OUTLINE)
        frect(scr, x, y, w, h, C("#3a1420"))
        frac = clamp(P.hp / P.max_hp, 0.0, 1.0)
        lag = clamp(P.hp_lag / P.max_hp, 0.0, 1.0)
        if lag > frac:
            frect(scr, x, y, w * lag, h, C("#ffd34d"))          # recent damage drains away in yellow
        if frac > 0:
            low = frac <= 0.25
            col = C("#ff9f6b") if (low and int(self.time * 6) % 2) else C("#e0405a")
            fw = max(1, rnd(w * frac))
            frect(scr, x, y, fw, h, col)
            frect(scr, x, y, fw, 1, C("#ff8fa3"))               # highlight along the top
        draw_text(scr, "%d/%d" % (max(0, P.hp), P.max_hp), x + w / 2, y + 1.5, (255, 255, 255), "center")

    def draw_hud(self, scr):
        P = self.P
        self.draw_health_bar(scr)
        if self.state == "hub":
            draw_text(scr, "EMBERKEEP CAMP", W / 2, 180, C("#ffd9b8"), "center")
            draw_text(scr, "%s  BEST %d" % (P.cls.name, self.best), 6, 180, C("#8d86b0"))
            draw_text(scr, "ESC: CLASS SELECT", W - 6, 180, C("#8d86b0"), "right")
            spr(scr, self.S["coin_a"], 206, 12)
            draw_text(scr, str(self.bank_coins), 212, 4, C("#ffd34d"))
            spr(scr, self.S["emerald"], 244, 12)
            draw_text(scr, str(self.bank_emeralds), 250, 4, C("#a6f2c4"))
            spr(scr, self.S["ruby"], 274, 12)
            draw_text(scr, str(self.bank_rubies), 280, 4, C("#ffa8b8"))
            return
        draw_text(scr, "WAVE %d" % self.wave, W / 2, 4, C("#f4efff"), "center")
        draw_text(scr, str(self.score), W - 6, 4, C("#f2c94c"), "right")
        flash = self.hud_flash > 0
        white = (255, 255, 255)
        spr(scr, self.S["coin_a"], 206, 12)
        draw_text(scr, str(self.coins), 212, 4, white if flash else C("#ffd34d"))
        spr(scr, self.S["emerald"], 244, 12)
        draw_text(scr, str(self.emeralds), 250, 4, white if flash else C("#a6f2c4"))
        spr(scr, self.S["ruby"], 274, 12)
        draw_text(scr, str(self.rubies), 280, 4, white if flash else C("#ffa8b8"))
        draw_text(scr, "%s  BEST %d" % (P.cls.name, self.best), 6, 180, C("#8d86b0"))
        draw_text(scr, "M: SOUND OFF" if self.sfx.muted else "M: SOUND ON", W - 6, 180, C("#8d86b0"), "right")

    def draw_title(self, scr):
        scr.blit(alpha_surf(CW, CH, (10, 6, 22), 0.72), (0, 0))
        draw_text(scr, "EMBERKEEP", W / 2, 14, C("#f2c94c"), "center", 4)
        draw_text(scr, "CHOOSE YOUR CLASS", W / 2, 38, C("#9fb4ff"), "center")
        if self.best > 0:
            draw_text(scr, "BEST %d" % self.best, W - 6, 4, C("#f2c94c"), "right")
        for i, c in enumerate(CLASSES):
            x = card_x(i)
            on = i == self.sel
            g = 2 if on else 1
            frect(scr, x - g, CARD_Y - g, CARD_W + g * 2, CARD_H + g * 2, C("#f2c94c") if on else C("#3a3560"))
            frect(scr, x, CARD_Y, CARD_W, CARD_H, C("#2a2248") if on else C("#1a1530"))
            frame = "idle1" if (on and int(self.time * 2) % 2) else "idle0"  # the chosen class breathes
            spr_big(scr, self.S["%s_%s" % (c.id, frame)], x + CARD_W / 2, CARD_Y + 46, 1.0 if on else 0.55)
            draw_text(scr, c.name, x + CARD_W / 2, CARD_Y + 52, (255, 255, 255) if on else C("#9a93bd"), "center")
            draw_text(scr, "HP %d" % c.hp, x + CARD_W / 2, CARD_Y + 62, C("#ff8fa3") if on else C("#6b6488"), "center")
        c = CLASSES[self.sel]
        draw_text(scr, c.line1, W / 2, 134, C("#f2c94c"), "center")
        draw_text(scr, c.line2, W / 2, 146, C("#c9c2e8"), "center")
        draw_text(scr, "A/D OR CLICK TO PICK, SPACE STARTS", W / 2, 164, (255, 255, 255), "center")
        draw_text(scr, "WASD MOVE  SPACE ATTACK  SHIFT DASH", W / 2, 176, C("#8d86b0"), "center")
        self.draw_volume_panel(scr)

    def draw_pause(self, scr):
        scr.blit(alpha_surf(CW, CH, (10, 6, 22), 0.72), (0, 0))
        if self.confirm:
            title = {"menu": "CHANGE CLASS?", "camp": "BACK TO CAMP?"}.get(self.confirm, "RESTART?")
            yes = {"menu": "C: YES", "camp": "H: YES"}.get(self.confirm, "R: YES")
            draw_text(scr, title, W / 2, 54, C("#ff9f6b"), "center", 4)
            draw_text(scr, "THIS RUN WILL BE LOST", W / 2, 86, C("#c9c2e8"), "center")
            draw_text(scr, yes, W / 2, 112, (255, 255, 255), "center")
            draw_text(scr, "P OR CLICK: KEEP PLAYING", W / 2, 126, C("#9fb4ff"), "center")
        else:
            draw_text(scr, "PAUSED", W / 2, 54, C("#f2c94c"), "center", 4)
            draw_text(scr, "P OR CLICK: RESUME", W / 2, 90, (255, 255, 255), "center")
            draw_text(scr, "R: RESTART", W / 2, 106, C("#9fb4ff"), "center")
            draw_text(scr, "H: BACK TO CAMP", W / 2, 122, C("#9fb4ff"), "center")
            draw_text(scr, "C: CHANGE CLASS", W / 2, 138, C("#9fb4ff"), "center")

    def draw_over(self, scr):
        P = self.P
        scr.blit(alpha_surf(CW, CH, (10, 6, 22), 0.68), (0, 0))
        draw_text(scr, "YOU FELL", W / 2, 34, C("#ff4d6d"), "center", 4)
        draw_text(scr, P.cls.name, W / 2, 64, C("#9fb4ff"), "center")
        draw_text(scr, "WAVE %d   SCORE %d" % (self.wave, self.score), W / 2, 76, (255, 255, 255), "center")
        draw_text(scr, "MONSTERS SLAIN %d" % self.kills, W / 2, 88, C("#f2c94c"), "center")
        draw_text(scr, "COINS %d" % self.coins, W / 2, 100, C("#ffd34d"), "center")
        draw_text(scr, "EMERALDS %d   RUBIES %d" % (self.emeralds, self.rubies), W / 2, 112, C("#a6f2c4"), "center")
        draw_text(scr, "BEST %d" % self.best, W / 2, 124, C("#9fb4ff"), "center")
        if self.over_t <= 0:
            if int(self.time * 2) % 2 == 0:
                draw_text(scr, "SPACE OR CLICK: RETRY", W / 2, 138, (255, 255, 255), "center")
            draw_text(scr, "H: BACK TO CAMP", W / 2, 150, C("#c9c2e8"), "center")
            draw_text(scr, "C: CHANGE CLASS", W / 2, 162, C("#c9c2e8"), "center")

    # ---- events / main loop -------------------------------------------
    def handle_event(self, ev):
        if ev.type == pygame.QUIT:
            self.quit()
        elif ev.type == pygame.KEYDOWN:
            k = ev.key
            if k == pygame.K_F11:
                pygame.display.toggle_fullscreen()
                return
            if k == pygame.K_F1:
                self.dev_open = not self.dev_open
                return
            if self.dev_open and pygame.K_F2 <= k <= pygame.K_F9:
                self.dev_action(k - pygame.K_F2)
                return
            if k in (pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET, pygame.K_COMMA, pygame.K_PERIOD):
                idx = 0 if k in (pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET) else 1
                step = -0.05 if k in (pygame.K_LEFTBRACKET, pygame.K_COMMA) else 0.05
                self.set_volume(idx, (self.vol_music if idx == 0 else self.vol_sfx) + step)
                self._write_save()
                if idx == 1:
                    self.sfx.play("select")
                return
            if self.state == "splash":
                if k in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_j):
                    self.enter_menu()
                elif k == pygame.K_ESCAPE:
                    self.quit()
                elif k == pygame.K_m:
                    self.toggle_mute()
                return
            if self.state == "title":
                if k in (pygame.K_LEFT, pygame.K_a):
                    self.select_class(self.sel - 1)
                    return
                if k in (pygame.K_RIGHT, pygame.K_d):
                    self.select_class(self.sel + 1)
                    return
                if k in (pygame.K_1, pygame.K_2, pygame.K_3):
                    self.select_class(k - pygame.K_1)
                    return
                if k == pygame.K_ESCAPE:
                    self.state = "splash"
                    return
            if self.state == "hub" and self.shop_open:
                if k == pygame.K_ESCAPE:
                    self.close_shop()
                elif k in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                    self.buy_upgrade(k - pygame.K_1)
                return
            if self.state == "hub" and k == pygame.K_ESCAPE:
                self.to_menu()
                return
            if k == pygame.K_m:
                self.toggle_mute()
            elif k == pygame.K_h:
                self.press_camp()
            elif k in (pygame.K_p, pygame.K_ESCAPE):
                self.press_pause()
            elif k == pygame.K_r:
                self.press_restart()
            elif k == pygame.K_c:
                self.press_menu()
            elif k in (pygame.K_SPACE, pygame.K_j, pygame.K_RETURN, pygame.K_KP_ENTER):
                self.press_atk(None)
            elif k in (pygame.K_LSHIFT, pygame.K_RSHIFT, pygame.K_k):
                self.press_dash()
        elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            gx, gy = ev.pos[0] / SC, ev.pos[1] / SC
            idx = self.slider_at(gx, gy)
            if idx is not None:                       # clicking a volume slider never starts anything
                self.drag = idx
                self.drag_slider(idx, gx)
                return
            if self.dev_open:
                ridx = self.dev_row_at(gx, gy)
                if ridx is not None:
                    self.dev_action(ridx)
                    return
            if self.state == "splash":
                self.enter_menu()
            elif self.state == "title":
                self.title_tap(gx, gy)
            elif self.state == "hub" and self.shop_open:
                idx = self.shop_card_at(gx, gy)
                if idx is not None:
                    self.buy_upgrade(idx)
                else:
                    self.close_shop()
            elif self.state == "hub" and self.near_shop() and self.click_on_stall(gx, gy):
                self.open_shop()
            elif self.state not in ("play", "hub"):
                self.start_game()
            else:
                self.press_atk(math.atan2(gy - self.P.y, gx - self.P.x))
        elif ev.type == pygame.MOUSEMOTION and self.drag is not None:
            self.drag_slider(self.drag, ev.pos[0] / SC)
        elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and self.drag is not None:
            if self.drag == 1:
                self.sfx.play("select")
            self.drag = None
            self._write_save()
        elif ev.type == getattr(pygame, "MOUSEWHEEL", -1):
            mx, my = pygame.mouse.get_pos()
            idx = self.slider_at(mx / SC, my / SC)
            if idx is not None:
                self.set_volume(idx, (self.vol_music if idx == 0 else self.vol_sfx) + 0.05 * ev.y)
                self._write_save()
        elif ev.type == getattr(pygame, "WINDOWFOCUSLOST", -1):
            if self.state == "play" and not self.paused:
                self.paused, self.confirm = True, ""

    def quit(self):
        self._write_save()
        pygame.quit()
        sys.exit()

    def run(self):
        while True:
            dt = min(0.05, self.clock.tick(60) / 1000.0)
            for ev in pygame.event.get():
                self.handle_event(ev)
            self.music.update()
            self.music.set_paused(self.state == "play" and self.paused)
            self.update(dt, pygame.key.get_pressed())
            self.draw()
            pygame.display.flip()


def main():
    Game().run()


if __name__ == "__main__":
    main()
