# Scroll Counter

A Windows Python script that counts vertical scrolling from a mouse wheel or a Precision Touchpad. 

Working globally, regardless of focused application.

## Requirements

- **Windows ONLY**
- Python 3.10 or newer
- No third-party packages

## Run

Go straightforward to .exe release. Notice executable only allows `down` mode.

## Choose a Mode

Open `scroll_counter.py` and change `COUNT_MODE` near the top:

```python
COUNT_MODE = "down"
```

- `"down"` counts downward scrolling only.
- `"both"` counts scrolling in both directions.
