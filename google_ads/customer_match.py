"""
Google Ads Customer Match — lógica de upload via HubSpot + Data Manager API

Critérios disponíveis:
  clientes-exclusao  Contatos com deal closedwon
  leads-hubspot      Contatos com deal >= Reuniao em serviços HubSpot
  leads-dev          Contatos com deal >= Reuniao em serviços de site/web
  leads-pagos        Contatos paid search com deal >= SQL
"""

import hashlib
import json
import os
import urllib.error
import urllib.request

from google_ads.lib import init_client, get_access_token

STAGES_REUNIAO_PLUS = [
    "appointmentscheduled",
    "qualifiedtobuy",
    "presentationscheduled",
    "decisionmakerboughtin",
    "22776105",
    "closedwon",
]

KEYWORDS_HUBSPOT = ["hubspot", "implantacao", "implantacao", "sustentacao", "sustentacao", "crm", "parceria", "migracao", "migracao"]
KEYWORDS_DEV = ["site", "wordpress", "web", "landing", "lp ", "institucional", "e-commerce", "ecommerce"]

CRITERIO_NAMES = {
    "clientes-exclusao": ("clientes-exclusao", "Clientes com negocio fechado (closedwon) - exclusao de campanhas"),
    "leads-hubspot": ("leads-hubspot", "Leads com reuniao agendada em servicos HubSpot"),
    "leads-dev": ("leads-dev", "Leads com reuniao agendada em servicos de desenvolvimento web"),
    "leads-pagos": ("leads-pagos", "Leads originados de midia paga com deal >= SQL"),
}


# ---------------------------------------------------------------------------
# HubSpot helpers
# ---------------------------------------------------------------------------

def _hs_post(token, path, body):
    url = f"https://api.hubapi.com{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise Exception(f"HubSpot {e.code} em {path}: {e.read().decode()}")


def _get_deal_ids_by_stage(token, stages):
    deal_ids = []
    after = None
    while True:
        body = {
            "filterGroups": [{"filters": [
                {"propertyName": "dealstage", "operator": "IN", "values": stages}
            ]}],
            "properties": ["dealname", "dealstage"],
            "limit": 100,
        }
        if after:
            body["after"] = after
        resp = _hs_post(token, "/crm/v3/objects/deals/search", body)
        results = resp.get("results", [])
        deal_ids.extend(r["id"] for r in results)
        after = resp.get("paging", {}).get("next", {}).get("after")
        if not after or not results:
            break
    return deal_ids


def _get_deal_ids_by_stage_and_name(token, stages, name_keywords):
    all_ids = _get_deal_ids_by_stage(token, stages)
    if not all_ids:
        return []
    filtered = []
    for i in range(0, len(all_ids), 100):
        batch = all_ids[i:i + 100]
        resp = _hs_post(token, "/crm/v3/objects/deals/batch/read", {
            "inputs": [{"id": did} for did in batch],
            "properties": ["dealname"],
        })
        for r in resp.get("results", []):
            name = r.get("properties", {}).get("dealname", "").lower()
            if any(kw.lower() in name for kw in name_keywords):
                filtered.append(r["id"])
    return filtered


def _contacts_from_deal_ids(token, deal_ids):
    if not deal_ids:
        return []
    contact_ids = set()
    for i in range(0, len(deal_ids), 100):
        batch = deal_ids[i:i + 100]
        resp = _hs_post(token, "/crm/v3/associations/deals/contacts/batch/read", {
            "inputs": [{"id": did} for did in batch]
        })
        for item in resp.get("results", []):
            for assoc in item.get("to", []):
                contact_ids.add(assoc["id"])
    if not contact_ids:
        return []
    emails = []
    for i in range(0, len(list(contact_ids)), 100):
        batch = list(contact_ids)[i:i + 100]
        resp = _hs_post(token, "/crm/v3/objects/contacts/batch/read", {
            "inputs": [{"id": cid} for cid in batch],
            "properties": ["email"],
        })
        for r in resp.get("results", []):
            email = (r.get("properties", {}).get("email", "") or "").lower().strip()
            if email and "@" in email:
                emails.append(email)
    return list(set(emails))


def _get_emails_for_criterio(token, criterio):
    if criterio == "clientes-exclusao":
        deal_ids = _get_deal_ids_by_stage(token, ["closedwon"])
        return _contacts_from_deal_ids(token, deal_ids)

    if criterio == "leads-hubspot":
        deal_ids = _get_deal_ids_by_stage_and_name(token, STAGES_REUNIAO_PLUS, KEYWORDS_HUBSPOT)
        return _contacts_from_deal_ids(token, deal_ids)

    if criterio == "leads-dev":
        deal_ids = _get_deal_ids_by_stage_and_name(token, STAGES_REUNIAO_PLUS, KEYWORDS_DEV)
        return _contacts_from_deal_ids(token, deal_ids)

    if criterio == "leads-pagos":
        stages_sql_plus = STAGES_REUNIAO_PLUS + ["20440236"]
        all_deal_ids = _get_deal_ids_by_stage(token, stages_sql_plus)
        contact_ids = set()
        for i in range(0, len(all_deal_ids), 100):
            batch = all_deal_ids[i:i + 100]
            resp = _hs_post(token, "/crm/v3/associations/deals/contacts/batch/read", {
                "inputs": [{"id": did} for did in batch]
            })
            for item in resp.get("results", []):
                for assoc in item.get("to", []):
                    contact_ids.add(assoc["id"])
        emails = []
        for i in range(0, len(list(contact_ids)), 100):
            batch = list(contact_ids)[i:i + 100]
            resp = _hs_post(token, "/crm/v3/objects/contacts/batch/read", {
                "inputs": [{"id": cid} for cid in batch],
                "properties": ["email", "hs_analytics_source"],
            })
            for r in resp.get("results", []):
                source = r.get("properties", {}).get("hs_analytics_source", "") or ""
                email = (r.get("properties", {}).get("email", "") or "").lower().strip()
                if source in ("PAID_SEARCH", "PAID_SOCIAL") and email and "@" in email:
                    emails.append(email)
        return list(set(emails))

    raise ValueError(f"Criterio desconhecido: {criterio}")


# ---------------------------------------------------------------------------
# Google Ads — criar lista Customer Match
# ---------------------------------------------------------------------------

def _create_user_list(customer_id, criterio):
    client = init_client()
    name, description = CRITERIO_NAMES[criterio]

    user_list_service = client.get_service("UserListService")
    op = client.get_type("UserListOperation")
    user_list = op.create
    user_list.name = name
    user_list.description = description
    user_list.membership_status = client.enums.UserListMembershipStatusEnum.OPEN
    user_list.membership_life_span = 540
    crm = user_list.crm_based_user_list
    crm.upload_key_type = client.enums.CustomerMatchUploadKeyTypeEnum.CONTACT_INFO
    crm.data_source_type = client.enums.UserListCrmDataSourceTypeEnum.FIRST_PARTY

    response = user_list_service.mutate_user_lists(
        customer_id=str(customer_id),
        operations=[op],
    )
    return response.results[0].resource_name.split("/")[-1]


# ---------------------------------------------------------------------------
# Data Manager API — upload hashed emails
# ---------------------------------------------------------------------------

def _upload_emails(customer_id, list_id, emails, dry_run=False):
    hashed = [hashlib.sha256(e.lower().strip().encode()).hexdigest() for e in emails]

    if dry_run:
        return {"dry_run": True, "total": len(hashed), "exemplo": hashed[0] if hashed else None}

    access_token = get_access_token(["https://www.googleapis.com/auth/datamanager"])
    url = "https://datamanager.googleapis.com/v1/audienceMembers:ingest"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    login_customer_id = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "").strip()
    batch_size = 10000
    total_sent = 0

    for i in range(0, len(hashed), batch_size):
        batch = hashed[i:i + batch_size]
        body = {
            "encoding": "HEX",
            "termsOfService": {"customerMatchTermsOfServiceStatus": "ACCEPTED"},
            "destinations": [{
                "loginAccount": {"accountType": "GOOGLE_ADS", "accountId": login_customer_id},
                "operatingAccount": {"accountType": "GOOGLE_ADS", "accountId": str(customer_id)},
                "productDestinationId": str(list_id),
            }],
            "audienceMembers": [
                {"userData": {"userIdentifiers": [{"emailAddress": h}]}}
                for h in batch
            ],
        }
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                json.loads(resp.read())
                total_sent += len(batch)
        except urllib.error.HTTPError as e:
            raise Exception(f"Data Manager API {e.code}: {e.read().decode()[:1000]}")

    return {"total": total_sent}


# ---------------------------------------------------------------------------
# Entrypoint principal
# ---------------------------------------------------------------------------

def run_upload_from_hubspot_list(hubspot_list_id: int, google_ads_list_id: str, customer_id: str, dry_run: bool = False) -> dict:
    hs_token = os.environ.get("HUBSPOT_TOKEN_ACONCAIA")
    if not hs_token:
        raise EnvironmentError("HUBSPOT_TOKEN_ACONCAIA nao definido")

    import urllib.request as _req
    emails = []
    vid_offset = None
    while True:
        url = f"https://api.hubapi.com/contacts/v1/lists/{hubspot_list_id}/contacts/all?count=100&property=email"
        if vid_offset:
            url += f"&vidOffset={vid_offset}"
        req = _req.Request(url, headers={"Authorization": f"Bearer {hs_token}"})
        with _req.urlopen(req) as r:
            data = json.loads(r.read())
        for c in data.get("contacts", []):
            email = (c.get("properties", {}).get("email", {}).get("value", "") or "").lower().strip()
            if email and "@" in email:
                emails.append(email)
        if not data.get("has-more"):
            break
        vid_offset = data.get("vid-offset")
    emails = list(set(emails))

    if not emails:
        return {"hubspot_list_id": hubspot_list_id, "google_ads_list_id": google_ads_list_id, "emails_encontrados": 0, "enviados": 0}

    result = _upload_emails(customer_id, google_ads_list_id, emails, dry_run=dry_run)
    return {
        "hubspot_list_id": hubspot_list_id,
        "google_ads_list_id": google_ads_list_id,
        "emails_encontrados": len(emails),
        **result,
    }


def run_upload(criterio: str, customer_id: str, list_id: str | None = None, dry_run: bool = False) -> dict:
    if criterio not in CRITERIO_NAMES:
        raise ValueError(f"Criterio invalido: {criterio}. Opcoes: {list(CRITERIO_NAMES)}")

    hs_token = os.environ.get("HUBSPOT_TOKEN_ACONCAIA")
    if not hs_token:
        raise EnvironmentError("HUBSPOT_TOKEN_ACONCAIA nao definido")

    # Criar lista se não informada
    created_list = False
    if not list_id:
        list_id = _create_user_list(customer_id, criterio)
        created_list = True

    # Buscar emails no HubSpot
    emails = _get_emails_for_criterio(hs_token, criterio)
    if not emails:
        return {"criterio": criterio, "list_id": list_id, "emails_encontrados": 0, "enviados": 0}

    # Upload
    result = _upload_emails(customer_id, list_id, emails, dry_run=dry_run)

    return {
        "criterio": criterio,
        "list_id": list_id,
        "lista_criada": created_list,
        "emails_encontrados": len(emails),
        **result,
    }
