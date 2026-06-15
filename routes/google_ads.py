import os
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from typing import Optional

from google_ads.customer_match import run_upload

router = APIRouter(tags=["Google Ads"])


def require_api_key(x_api_key: str = Header(...)):
    key = os.environ.get("API_KEY", "")
    if key and x_api_key != key:
        raise HTTPException(status_code=401, detail="Unauthorized")


class CustomerMatchBody(BaseModel):
    criterio: str
    customer_id: Optional[str] = None
    list_id: Optional[str] = None
    dry_run: bool = False


@router.post("/customer-match", dependencies=[Depends(require_api_key)])
def customer_match(body: CustomerMatchBody):
    customer_id = body.customer_id or os.environ.get("GOOGLE_ADS_CUSTOMER_ID", "")
    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id obrigatorio")
    return run_upload(
        criterio=body.criterio,
        customer_id=customer_id,
        list_id=body.list_id,
        dry_run=body.dry_run,
    )
