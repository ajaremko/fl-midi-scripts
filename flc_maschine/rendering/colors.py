"""
Colours for LEDs set to Color Mode = HSB in the template. The script sends an LED's hue,
saturation and brightness as three 0-127 values, so frames hold (hue, saturation, brightness)
tuples.
"""

MAX = 127

OFF = (0, 0, 0)
WHITE = (0, 0, MAX)


def rgb_to_hsb(color):
    """Convert an FL Studio colour (0xRRGGBB, as channels.getChannelColor returns) to an HSB tuple."""
    color &= 0xFFFFFF
    r = (color >> 16) & 0xFF
    g = (color >> 8) & 0xFF
    b = color & 0xFF

    high = max(r, g, b)
    low = min(r, g, b)
    spread = high - low

    if spread == 0:
        hue = 0.0
    elif high == r:
        hue = ((g - b) / spread) % 6
    elif high == g:
        hue = (b - r) / spread + 2
    else:
        hue = (r - g) / spread + 4
    saturation = spread / high if high else 0.0

    return (round(hue / 6 * MAX) % (MAX + 1), round(saturation * MAX), round(high / 255 * MAX))


def with_brightness(hsb, brightness):
    return (hsb[0], hsb[1], brightness)
