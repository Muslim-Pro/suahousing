import re


def tanzania_whatsapp_number(phone):
    # Tengeneza kiungo cha WhatsApp kwa namba za simu za Tanzania zilizo halali.
    digits = re.sub(r'\D', '', phone or '')
    if digits.startswith('00'):
        digits = digits[2:]
    if digits.startswith('0') and len(digits) == 10:
        digits = f'255{digits[1:]}'
    elif len(digits) == 9:
        digits = f'255{digits}'
    if digits.startswith('255') and len(digits) == 12 and digits[3] in '6789':
        return digits
    return ''
