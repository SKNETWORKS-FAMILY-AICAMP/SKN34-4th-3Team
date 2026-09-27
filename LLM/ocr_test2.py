import asyncio
from src.models import get_llm
from src.rag.backend_tasks import extract_receipt_from_ocr

ocr_text = """1(90%): 농심마트 강남점
2(85%): 2026-09-22
3(88%): 농심 올리브 짜파게티
4(70%): 4,980
5(82%): 농심 감자면
6(65%): 3,500
7(90%): 합계
8(90%): 8,480
9(75%): 카드결제
"""

async def main():
    llm = get_llm()
    result = await extract_receipt_from_ocr(llm, ocr_text=ocr_text)
    print(result.model_dump())

asyncio.run(main())
