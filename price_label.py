#!/usr/bin/env python3
"""
Label Generator - Creates product labels from EAN codes
"""
import argparse
import requests
from PIL import Image, ImageDraw, ImageFont
import barcode
from barcode.writer import ImageWriter
from io import BytesIO


def format_price(price_minor_units, template='${price}'):
        """Format price from minor units using a template.

        Placeholders available in `template`:
            - {maj}: major units (integer)
            - {min}: minor units (two digits, zero-padded)
            - {price}: full price with dot separator (e.g. '1.50')

        Default template is '${price}' which yields the previous behaviour.
        Example: template='{maj}.{min} zł' -> '1.50 zł'
        """
        maj = price_minor_units // 100
        min_units = price_minor_units % 100
        price_str = f"{maj}.{min_units:02d}"
        return template.format(maj=maj, min=f"{min_units:02d}", price=price_str)


def fetch_product_info(ean_code, language='world'):
    """Fetch product information from Open Food Facts API

    Args:
        ean_code: EAN product code
        language: Language or domain prefix (e.g., 'en', 'pl', or 'world')
    """
    # Build domain based on requested language. Use 'world' for global dataset.
    if language and language != 'world':
        domain = f"{language}.openfoodfacts.org"
    else:
        domain = "world.openfoodfacts.org"

    url = f"https://{domain}/api/v0/product/{ean_code}.json"
    response = requests.get(url)
    
    if response.status_code != 200:
        raise Exception(f"Failed to fetch product info: HTTP {response.status_code}")
    
    data = response.json()
    
    if data.get('status') != 1:
        raise Exception(f"Product not found for EAN: {ean_code}")
    
    product = data.get('product', {})
    
    return {
        'name': product.get('product_name', 'Unknown Product'),
        'producer': product.get('brands', 'Unknown Brand'),
        'ean': ean_code
    }


def generate_barcode_image(ean_code):
    """Generate a barcode image for the given EAN code
    
    Args:
        ean_code: EAN-13 barcode string
    
    Returns:
        PIL Image object containing the barcode
    """
    from barcode import EAN13
    
    # Create barcode with ImageWriter
    ean = EAN13(ean_code, writer=ImageWriter())
    
    # Generate barcode in memory
    buffer = BytesIO()
    ean.write(buffer, options={
        'write_text': False,  # We'll add text separately
        'module_height': 8,
        'module_width': 0.2,
        'quiet_zone': 2,
    })
    
    buffer.seek(0)
    barcode_img = Image.open(buffer)
    
    return barcode_img


def create_label(ean_code, price_minor_units, output_file='label.png', language='world', price_format='${price}', 
                 custom_name=None, custom_producer=None):
    """
    Create a product label with specified dimensions and layout
    
    Args:
        ean_code: EAN product code
        price_minor_units: Price in minor currency units (e.g., 100 for $1.00)
        output_file: Output PNG filename
        language: Language or domain prefix for product lookup (e.g., 'en', 'pl', 'world')
        price_format: Template for formatting the price
        custom_name: Override product name from API
        custom_producer: Override producer from API
    """
    # Specifications
    DPI = 8  # dots per mm
    HEIGHT_MM = 48
    PADDING_LEFT_MM = 5
    
    # Convert mm to pixels
    height_px = int(HEIGHT_MM * DPI)
    padding_left_px = int(PADDING_LEFT_MM * DPI)
    padding_internal = int(3 * DPI)  # 3mm internal padding
    
    # Fetch product info or use custom data
    if custom_name and custom_producer:
        product_info = {
            'name': custom_name,
            'producer': custom_producer,
            'ean': ean_code
        }
    else:
        product_info = fetch_product_info(ean_code, language)
        # Allow partial override
        if custom_name:
            product_info['name'] = custom_name
        if custom_producer:
            product_info['producer'] = custom_producer
    
    # Format price
    price_text = format_price(price_minor_units, price_format)
    
    # Generate barcode
    barcode_img = generate_barcode_image(ean_code)
    
    # Create initial image to calculate left side width
    # We'll use a large temporary canvas
    temp_img = Image.new('RGB', (2000, height_px), 'white')
    draw = ImageDraw.Draw(temp_img)
    
    # Try to load fonts, fallback to default if not available
    try:
        # Large font for left side text
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", int(5 * DPI))
        # Very large font for price
        font_price = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", int(12 * DPI))
    except:
        try:
            font_large = ImageFont.truetype("arial.ttf", int(5 * DPI))
            font_price = ImageFont.truetype("arial.ttf", int(12 * DPI))
        except:
            font_large = ImageFont.load_default()
            font_price = ImageFont.load_default()
    
    # Calculate left side layout
    y_offset = padding_internal
    
    # Product name
    name_bbox = draw.textbbox((0, 0), product_info['name'], font=font_large)
    name_width = name_bbox[2] - name_bbox[0]
    name_height = name_bbox[3] - name_bbox[1]
    y_offset += name_height + int(1 * DPI)
    
    # Producer
    producer_bbox = draw.textbbox((0, 0), product_info['producer'], font=font_large)
    producer_width = producer_bbox[2] - producer_bbox[0]
    producer_height = producer_bbox[3] - producer_bbox[1]
    y_offset += producer_height + int(1 * DPI)
    
    # EAN text
    ean_text = f"EAN: {ean_code}"
    ean_bbox = draw.textbbox((0, 0), ean_text, font=font_large)
    ean_width = ean_bbox[2] - ean_bbox[0]
    ean_height = ean_bbox[3] - ean_bbox[1]
    y_offset += ean_height + int(1 * DPI)
    
    # Barcode (resize to fit)
    barcode_width = int(30 * DPI)  # 30mm wide
    barcode_height = int(10 * DPI)  # 10mm tall
    barcode_img = barcode_img.resize((barcode_width, barcode_height), Image.Resampling.LANCZOS)
    
    # Calculate left side width
    left_width = max(name_width, producer_width, ean_width, barcode_width) + padding_internal * 2
    
    # Calculate right side (price)
    price_bbox = draw.textbbox((0, 0), price_text, font=font_price)
    price_width = price_bbox[2] - price_bbox[0]
    price_height = price_bbox[3] - price_bbox[1]
    right_width = price_width + padding_internal * 2
    
    # Total width
    total_width = padding_left_px + left_width + right_width
    
    # Create final image
    img = Image.new('RGB', (total_width, height_px), 'white')
    draw = ImageDraw.Draw(img)
    
    # Draw left side content
    x_left = padding_left_px + padding_internal
    y_pos = padding_internal
    
    # Draw name
    draw.text((x_left, y_pos), product_info['name'], fill='black', font=font_large)
    y_pos += name_height + int(1 * DPI)
    
    # Draw producer
    draw.text((x_left, y_pos), product_info['producer'], fill='black', font=font_large)
    y_pos += producer_height + int(1 * DPI)
    
    # Draw EAN
    draw.text((x_left, y_pos), ean_text, fill='black', font=font_large)
    y_pos += ean_height + int(1 * DPI)
    
    # Draw barcode
    img.paste(barcode_img, (x_left, y_pos))
    
    # Draw right side (price) - centered vertically
    x_price = padding_left_px + left_width + padding_internal
    y_price = (height_px - price_height) // 2
    draw.text((x_price, y_price), price_text, fill='black', font=font_price)
    
    # Draw vertical separator line
    separator_x = padding_left_px + left_width
    draw.line([(separator_x, 0), (separator_x, height_px)], fill='black', width=2)
    
    # Save the image
    img.save(output_file, dpi=(DPI * 25.4, DPI * 25.4))  # Convert dots/mm to dots/inch
    print(f"Label saved to {output_file}")
    print(f"Dimensions: {total_width}x{height_px} pixels ({total_width/DPI:.1f}x{height_px/DPI:.1f}mm)")

def main():
    parser = argparse.ArgumentParser(
        description='Generate product labels from EAN codes',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 5449000000996 299 -o cola_label.png
  %(prog)s 3017620422003 150
        """
    )
    
    parser.add_argument('ean', type=str, help='EAN-13 barcode (13 digits)')
    parser.add_argument('price', type=int, help='Price in minor currency units (e.g., 100 for $1.00)')
    parser.add_argument('-o', '--output', type=str, default='label.png',
                        help='Output PNG filename (default: label.png)')
    parser.add_argument('-l', '--lang', type=str, default='world',
                        help='Language code or domain prefix for Open Food Facts (e.g., en, pl, world)')
    parser.add_argument('--price-format', dest='price_format', type=str, default='${price}',
                        help="Price format template using placeholders {maj}, {min}, {price} (default '${price}')")
    parser.add_argument('--name', type=str, default=None,
                        help='Override product name from API')
    parser.add_argument('--producer', type=str, default=None,
                        help='Override producer/brand from API')
    
    args = parser.parse_args()
    
    # Validate EAN
    if not args.ean.isdigit() or len(args.ean) != 13:
        parser.error("EAN must be exactly 13 digits")
    
    # Validate price
    if args.price < 0:
        parser.error("Price must be non-negative")
    
    try:
        create_label(args.ean, args.price, args.output, args.lang, price_format=args.price_format,
                    custom_name=args.name, custom_producer=args.producer)
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
