<!-- hand-written: describes the goal only; must not hint at the pitfall or the fix -->
I'm writing a small image-editing utility on top of numpy. Images are 2-D `uint8` arrays.
Please write `target.py` with `brighten_pixel(img, row, col, amount) -> int` that returns
the brightened value of a single pixel (pixel value plus `amount`), saturating at 255 rather
than going past it. Don't modify the image.
