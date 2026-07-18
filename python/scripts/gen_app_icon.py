"""Generate Valor app icon: 1024x1024, rounded square, deep gradient, gold V + red dot + agent nodes."""
from PIL import Image, ImageDraw
import numpy as np
import random

W = H = 1024
RADIUS = 180

arr = np.zeros((H, W, 3), dtype=np.uint8)
for y in range(H):
    t = y / H
    arr[y, :, 0] = int(12 + 36 * t)
    arr[y, :, 1] = int(20 + 52 * t)
    arr[y, :, 2] = int(38 + 80 * t)
bg = Image.fromarray(arr)

mask = Image.new('L', (W, H), 0)
ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (W, H)], radius=RADIUS, fill=255)

img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
img.paste(bg, (0, 0), mask)
draw = ImageDraw.Draw(img, 'RGBA')

GOLD = (244, 184, 96, 255)
RED = (230, 57, 70, 255)
WHITE = (255, 255, 255, 255)

V_TOP_Y = 220
V_BOT_Y = 600
V_CX = 512
V_HALF_W = 220
V_THICK = 64

draw.line([(V_CX - V_HALF_W, V_TOP_Y), (V_CX, V_BOT_Y)], fill=GOLD, width=V_THICK)
draw.line([(V_CX, V_BOT_Y), (V_CX + V_HALF_W, V_TOP_Y)], fill=GOLD, width=V_THICK)

for pos in [(V_CX - V_HALF_W, V_TOP_Y), (V_CX + V_HALF_W, V_TOP_Y)]:
    draw.ellipse(
        [(pos[0] - V_THICK // 2 - 2, pos[1] - V_THICK // 2 - 2),
         (pos[0] + V_THICK // 2 + 2, pos[1] + V_THICK // 2 + 2)],
        fill=GOLD,
    )

draw.ellipse(
    [(V_CX - V_THICK // 2 - 2, V_BOT_Y - V_THICK // 2 - 2),
     (V_CX + V_THICK // 2 + 2, V_BOT_Y + V_THICK // 2 + 2)],
    fill=GOLD,
)

RED_DOT_R = 56
RED_DOT_POS = (V_CX + V_HALF_W + 20, V_TOP_Y - 80)
draw.ellipse(
    [(RED_DOT_POS[0] - RED_DOT_R, RED_DOT_POS[1] - RED_DOT_R),
     (RED_DOT_POS[0] + RED_DOT_R, RED_DOT_POS[1] + RED_DOT_R)],
    fill=RED,
)

AGENT_Y = 800
AGENT_N = 5
AGENT_X_START = 200
AGENT_X_END = 824
agent_xs = [AGENT_X_START + i * (AGENT_X_END - AGENT_X_START) // (AGENT_N - 1) for i in range(AGENT_N)]

for i in range(AGENT_N - 1):
    draw.line(
        [(agent_xs[i], AGENT_Y), (agent_xs[i + 1], AGENT_Y)],
        fill=(255, 255, 255, 180),
        width=4,
    )

NODE_R = 22
for x in agent_xs:
    draw.ellipse(
        [(x - NODE_R, AGENT_Y - NODE_R), (x + NODE_R, AGENT_Y + NODE_R)],
        fill=WHITE,
    )
    draw.ellipse(
        [(x - NODE_R + 6, AGENT_Y - NODE_R + 6),
         (x + NODE_R - 6, AGENT_Y + NODE_R - 6)],
        fill=GOLD,
    )

random.seed(11)
for _ in range(80):
    x = random.randint(40, W - 40)
    y = random.randint(40, H - 40)
    r = random.choice([1, 1, 1, 2])
    draw.ellipse([(x - r, y - r), (x + r, y + r)], fill=(255, 255, 255, 40))

out = '/home/zhugenmi/work/FinTech/valor/frontend/app-icon.png'
img.save(out, 'PNG')
print(f'Saved to {out}, size={img.size}')
