import re


def normalize_tanzania_phone_number(phone):
    digits = re.sub(r'\D', '', phone or '')
    if digits.startswith('00'):
        digits = digits[2:]
    if digits.startswith('2550') and len(digits) == 13:
        digits = f'255{digits[4:]}'
    elif digits.startswith('0') and len(digits) == 10:
        digits = f'255{digits[1:]}'
    elif len(digits) == 9:
        digits = f'255{digits}'
    if digits.startswith('255') and len(digits) == 12 and digits[3] in '6789':
        return digits
    return None


def tanzania_whatsapp_number(phone):
    return normalize_tanzania_phone_number(phone) or ''
