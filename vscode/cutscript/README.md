# FiveFury CutScript VS Code Extension

Minimal VS Code support for FiveFury `.cuts` / `.cutscript` files.

## Features

- Syntax highlighting for CutScript commands, tracks, assets, options, constants and comments.
- Context-aware completion for root commands, assets, tracks, event commands, options and declared asset names.
- Snippet completions with argument placeholders, for example `OFFSET x y z` and camera `ROT pitch yaw roll`.
- Indentation-aware multiline snippets. Nested snippet lines preserve the current block indentation.
- Auto-indent after `ASSETS`, `TRACK ...` and `LIGHT ...`, with `END` closing sections.
- Colon-marked subblocks for long asset and camera declarations, for example `PROP name:` and `0.000 CUT cam:`.
- Completion details explaining argument order and meaning.
- Hover documentation for commands, options, tracks and flags.
- Compile command: `FiveFury: Compile CutScript to .cut`.

## Usage

1. Open this folder in VS Code:

   ```powershell
   code C:\Users\vicho\OneDrive\Documents\WalkerPy\vscode\cutscript
   ```

2. Press `F5` to launch an Extension Development Host.
3. Open a `.cuts` file.
4. Run `FiveFury: Compile CutScript to .cut` from the command palette.

The compile command calls:

```python
from fivefury import save_cutscript
save_cutscript(active_file)
```

Set `fivefuryCuts.pythonPath` if VS Code needs a specific Python executable.

If you installed a packaged `.vsix`, rebuild/reinstall after editing this folder:

```powershell
cd C:\Users\vicho\OneDrive\Documents\WalkerPy\vscode\cutscript
vsce package
code --install-extension .\fivefury-cutscript-0.1.0.vsix --force
```

## Example

```text
CUTSCENE "sample_scene"
DURATION 8.0
OFFSET 0 0 100
FLAGS PLAYABLE SECTIONED STORY_MODE

ASSETS
  ASSET_MANAGER assets
  ANIM_MANAGER anims
  CAMERA cam_main
  PROP stage:
    MODEL "stage01"
    YTYP "stage01"
  LIGHT key_light:
    TYPE SPOT
    POSITION 0 -3 4
    COLOR #ffd9b3
    INTENSITY 4
  FADE screen
END

TRACK LOAD
  0.000 SCENE "sample_scene"
  0.000 MODELS stage
END

TRACK CAMERA
  0.000 CUT cam_main:
    NAME "intro"
    POS 0 -7 3
    ROT 0 0 0
    NEAR 0.05
    FAR 1000
END

TRACK FADE
  0.000 OUT screen VALUE 1.0 COLOR 0xff000000
  0.500 IN screen VALUE 0.0 COLOR 0xff000000
END

SAVE "sample_scene.cut"
```
