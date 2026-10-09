# Bundled games and programs

Each game is a **folder of `.vm` files, one per Jack class**. That's exactly
what the nand2tetris Jack compiler produces, e.g.:

```
games/pong/
├── Main.vm        Main.main: the program starts here (called by Sys.init)
├── PongGame.vm    the game loop
├── Ball.vm        the ball
└── Bat.vm         the bat
```

Run one by name (from the `jackvm-py` folder), or choose it in the window:

```bash
python3 -m jackvm pong     # by name
python3 -m jackvm          # file picker: click [play 4 files] next to pong/
```

| Name | What it is | Controls | Files |
|------|------------|----------|-------|
| `pong` | Single-player Pong. Keep the ball in play with the bat. | ← → move the bat, Esc ends the game (hold Esc 1 s to close the player) | 4 |
| `space-invaders` | A Space Invaders clone. | Space starts / shoots, ← → move | 12 |
| `square-game` | Move a square around the screen. | Arrow keys move, Z = smaller, X = bigger, Q = quit | 3 |
| `average` | Asks for some numbers and prints their average. | Type numbers, press Enter after each | 9 |
| `hello-world` | Prints "Hello world!" and stops. | none | 1 |

Sources: `pong`, `square-game`, `average`, `hello-world` come from the
[nand2tetris software suite](https://www.nand2tetris.org/software).
`space-invaders` is from [jcon/SpaceInvaders](https://github.com/jcon/SpaceInvaders).
These are the programs the original jackvm-rs site ships. There they're
single combined files; here they're split back into one file per class.

`average/` includes its own copy of the Jack OS classes (`Math.vm`,
`Sys.vm`, ...), so the VM runs it as-is. The other games contain only their
own classes, so the built-in OS is added automatically.

**Add your own:** copy your compiled game's folder (all its `.vm` files) in
here. It then shows up in the picker and you can run it by its folder name.
A single `.vm` file dropped in here works too.
