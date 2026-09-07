# Scroll Counter

A Windows Python script that counts vertical scrolling from a mouse wheel or a Precision Touchpad. It keeps working while another application is focused.

## Requirements

- **Windows ONLY**
- Python 3.10 or newer
- No third-party packages

## Choose a Mode

Open `scroll_counter.py` and change `COUNT_MODE` near the top:

```python
COUNT_MODE = "down"
```

- `"down"` counts downward scrolling only.
- `"both"` counts scrolling in both directions.

## Run

```powershell
python scroll_counter.py
```

Scroll with a mouse wheel or use two fingers on the touchpad. Press `Ctrl+C` to stop.

The result is shown in normalized pixels. It may not exactly match the distance shown inside every application because applications handle scrolling differently.
