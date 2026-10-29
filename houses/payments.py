import hashlib
import hmac
import json
import logging

import requests
from django.conf import settings
from django.core.cache import cache


logger = logging.getLogger(__name__)


class ClickPesaError(Exception):
    def __init__(self, message, *, request_may_have_been_sent=False):
        super().__init__(message)
        self.request_may_have_been_sent = request_may_have_been_sent


def send_clickpesa_ussd_push(*, phone_number, amount, order_reference):
    client_id = getattr(settings, 'CLICKPESA_CLIENT_ID', '').strip()
    api_key = getattr(settings, 'CLICKPESA_API_KEY', '').strip()
    checksum_key = getattr(settings, 'CLICKPESA_CHECKSUM', '').strip()
    base_url = getattr(
        settings,
        'CLICKPESA_BASE_URL',
        'https://api.clickpesa.com/third-parties',
    ).strip().rstrip('/')

    if not client_id or not api_key or not checksum_key:
        raise ClickPesaError(
            'Mobile money payments are not configured. Please contact support.',
        )

    token_cache_key = 'clickpesa_token_' + hashlib.sha256(
        f'{base_url}:{client_id}:{api_key}:{checksum_key}'.encode('utf-8'),
    ).hexdigest()
    jwt_token = cache.get(token_cache_key)

    if not jwt_token:
        try:
            token_response = requests.post(
                f'{base_url}/generate-token',
                headers={
                    'client-id': client_id,
                    'api-key': api_key,
                    'Content-Type': 'application/json',
                },
                timeout=15,
            )
        except requests.RequestException as error:
            logger.exception('ClickPesa token request failed.')
            raise ClickPesaError(
                'Could not connect to the payment service. Please try again.',
            ) from error

        if token_response.status_code not in (200, 201):
            logger.error(
                'ClickPesa token request returned HTTP %s.',
                token_response.status_code,
            )
            raise ClickPesaError(
                'The payment service could not authorize this request. Please try again.',
            )

        try:
            token_data = token_response.json()
        except ValueError as error:
            logger.exception('ClickPesa returned invalid token response JSON.')
            raise ClickPesaError(
                'The payment service returned an invalid response. Please try again.',
            ) from error

        jwt_token = token_data.get('token') or token_data.get('accessToken')
        if not jwt_token:
            logger.error('ClickPesa token response did not contain an access token.')
            raise ClickPesaError(
                'The payment service could not authorize this request. Please try again.',
            )
        cache.set(token_cache_key, jwt_token, timeout=55 * 60)

    payload = {
        'amount': str(amount),
        'currency': 'TZS',
        'orderReference': order_reference,
        'phoneNumber': phone_number,
    }
    payload_json = json.dumps(payload, separators=(',', ':'), sort_keys=True)
    payload['checksum'] = hmac.new(
        checksum_key.encode('utf-8'),
        payload_json.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()

    try:
        push_response = requests.post(
            f'{base_url}/payments/initiate-ussd-push-request',
            json=payload,
            headers={
                'Authorization': jwt_token,
                'Content-Type': 'application/json',
            },
            timeout=15,
        )
    except requests.RequestException as error:
        logger.exception('ClickPesa USSD push request outcome is unknown.')
        raise ClickPesaError(
            'We could not confirm whether the USSD request reached your phone. '
            'Check your phone before trying again, or contact your landlord.',
            request_may_have_been_sent=True,
        ) from error

    if push_response.status_code not in (200, 201, 202):
        logger.error(
            'ClickPesa USSD push request returned HTTP %s.',
            push_response.status_code,
        )
        if push_response.status_code == 401:
            cache.delete(token_cache_key)
        if push_response.status_code >= 500:
            raise ClickPesaError(
                'The payment service response is unclear. Check your phone before trying again, '
                'or contact your landlord.',
                request_may_have_been_sent=True,
            )
        raise ClickPesaError(
            'The payment request was not accepted. Check your number and try again.',
        )
