import os


def init_client():
    from google.ads.googleads.client import GoogleAdsClient

    config = {
        "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "use_proto_plus": True,
    }
    login_id = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "").replace("-", "")
    if login_id:
        config["login_customer_id"] = login_id

    return GoogleAdsClient.load_from_dict(config)


def get_access_token(scopes: list[str]) -> str:
    import google.oauth2.credentials
    import google.auth.transport.requests

    creds = google.oauth2.credentials.Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GOOGLE_ADS_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        scopes=scopes,
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token
