"""Conservative pre-dispatch estimates, not a provider billing guarantee."""
import math
from decimal import Decimal, ROUND_CEILING
from ..baselines.contract import canonical

MODEL = 'gpt-5.4-mini-2026-03-17'
ENDPOINT = 'https://api.openai.com/v1/chat/completions'
INPUT_LIMIT = 16384
OUTPUT_LIMIT = 4096
RESERVE_USD = Decimal('0.04')
INPUT_RATE = Decimal('0.75')
OUTPUT_RATE = Decimal('4.50')
SOURCES = {
    'retrieved_date': '2026-10-27',
    'pricing': 'https://developers.openai.com/api/docs/models/gpt-5.4-mini',
    'image_rules': 'https://developers.openai.com/api/docs/guides/images-vision',
    'spend_controls': 'https://developers.openai.com/api/docs/guides/spend-limits',
    'rates_per_million_usd': {'input': '0.75', 'cached_input': '0.075', 'output': '4.50'},
    'image_patch': 32, 'image_multiplier': '1.2', 'high_patch_budget': 2500,
}


def image_tokens(width, height):
    patches = math.ceil(width/32)*math.ceil(height/32)
    if patches > 2500 or max(width,height) > 2048:
        raise ValueError('This frozen plan does not permit images needing provider resizing')
    return math.ceil(patches*1.2)


def estimate(body, sizes):
    if body['model'] != MODEL or body.get('max_completion_tokens') != OUTPUT_LIMIT or body.get('reasoning_effort') != 'none':
        raise ValueError('Model/settings differ from the approved proposal')
    content=[]
    image_count=0
    for item in body['messages'][1]['content']:
        if item['type']=='image_url':
            if item['image_url']['detail']!='high':raise ValueError('Image detail differs')
            image_count+=1
        else:content.append(item)
    if len(sizes)!=image_count:raise ValueError('Image dimensions missing')
    image_count_tokens=sum(image_tokens(*s) for s in sizes)
    text={'system':body['messages'][0]['content'],'text':content,'response_format':body['response_format']}
    # shortcut: UTF-8 byte ceiling plus 2,048 framing tokens, revisit if live usage exceeds it.
    text_bytes=len(canonical(text).encode('utf-8'))
    text_estimate=text_bytes+2048
    total=text_estimate+image_count_tokens
    if total>INPUT_LIMIT:raise ValueError('Estimated input exceeds pre-dispatch token limit')
    cost=(Decimal(total)*INPUT_RATE+Decimal(OUTPUT_LIMIT)*OUTPUT_RATE)/Decimal(1000000)
    if cost*Decimal('1.25')>RESERVE_USD:raise ValueError('Reservation cannot cover estimate plus safety margin')
    return {'image_tokens':image_count_tokens,'text_utf8_bytes':text_bytes,'text_token_bound_with_framing':text_estimate,
            'input_token_estimate':total,'maximum_output_tokens':OUTPUT_LIMIT,'estimated_usd_at_max_output':str(cost),
            'reservation_usd':str(RESERVE_USD)}
