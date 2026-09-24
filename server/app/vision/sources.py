"""Build stream URLs for common IP-camera vendors and resolve ONVIF streams."""
import base64
import hashlib
import os
import re
from datetime import datetime, timezone
from urllib.parse import quote

VENDORS = {
    "axis": "Axis (VAPIX)",
    "hikvision": "Hikvision / HiLook",
    "dahua": "Dahua / Imou",
    "uniview": "Uniview (UNV)",
    "hanwha": "Hanwha / Samsung Wisenet",
    "bosch": "Bosch",
    "vivotek": "Vivotek",
    "milesight": "Milesight",
    "tiandy": "Tiandy",
    "onvif": "ONVIF (همه برندها)",
    "rtsp": "RTSP دستی",
    "http_mjpeg": "HTTP / MJPEG",
    "file": "فایل ویدیو (آزمایشی)",
    "usb": "وب‌کم / USB",
}


def _auth(cam):
    if not cam.get("username"):
        return ""
    return f"{quote(cam['username'], safe='')}:{quote(cam.get('password') or '', safe='')}@"


def build_url(cam: dict) -> str:
    """Return a capture URL (rtsp/http/path/index) for a camera config dict."""
    vendor = cam.get("vendor") or "rtsp"
    # An explicit URL always wins (for ONVIF it caches the resolved stream URI).
    if cam.get("url"):
        return cam["url"]
    host = cam.get("host") or ""
    ch = int(cam.get("channel") or 1)
    sub = (cam.get("stream") or "main") == "sub"
    port = cam.get("port") or 554
    base = f"rtsp://{_auth(cam)}{host}:{port}"

    if vendor == "axis":
        q = f"camera={ch}" + ("&resolution=640x360&fps=10" if sub else "")
        return f"{base}/axis-media/media.amp?videocodec=h264&{q}"
    if vendor == "hikvision":
        return f"{base}/Streaming/Channels/{ch}0{2 if sub else 1}"
    if vendor == "dahua":
        return f"{base}/cam/realmonitor?channel={ch}&subtype={1 if sub else 0}"
    if vendor == "uniview":
        return f"{base}/unicast/c{ch}/s{1 if sub else 0}/live"
    if vendor == "hanwha":
        return f"{base}/profile{3 if sub else 2}/media.smp"
    if vendor == "bosch":
        return f"{base}/?inst={2 if sub else 1}"
    if vendor == "vivotek":
        return f"{base}/live{2 if sub else 1}.sdp"
    if vendor == "milesight":
        return f"{base}/{'sub' if sub else 'main'}"
    if vendor == "tiandy":
        return f"{base}/{ch}/{2 if sub else 1}"
    if vendor == "onvif":
        return resolve_onvif(cam)
    if vendor == "http_mjpeg":
        return cam.get("url") or f"http://{_auth(cam)}{host}:{cam.get('port') or 80}/"
    if vendor == "usb":
        return str(cam.get("url") or "0")
    return cam.get("url") or base


def snapshot_url(cam: dict):
    """Vendor HTTP snapshot endpoint (used by the UI 'test connection' when available)."""
    host = cam.get("host")
    if not host:
        return None
    ch = int(cam.get("channel") or 1)
    vendor = cam.get("vendor")
    if vendor == "axis":
        return f"http://{host}/axis-cgi/jpg/image.cgi?camera={ch}"
    if vendor == "hikvision":
        return f"http://{host}/ISAPI/Streaming/channels/{ch}01/picture"
    if vendor == "dahua":
        return f"http://{host}/cgi-bin/snapshot.cgi?channel={ch}"
    return None


# ---------------------------------------------------------------- ONVIF (minimal SOAP client)
_SOAP = """<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
 xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">
<s:Header>{security}</s:Header><s:Body>{body}</s:Body></s:Envelope>"""


def _ws_security(user, password):
    if not user:
        return ""
    nonce = os.urandom(16)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + (password or "").encode()).digest()).decode()
    return (
        '<Security s:mustUnderstand="1" xmlns="http://docs.oasis-open.org/wss/2004/01/'
        'oasis-200401-wss-wssecurity-secext-1.0.xsd"><UsernameToken>'
        f"<Username>{user}</Username>"
        '<Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0'
        f'#PasswordDigest">{digest}</Password>'
        '<Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0'
        f'#Base64Binary">{base64.b64encode(nonce).decode()}</Nonce>'
        '<Created xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">'
        f"{created}</Created></UsernameToken></Security>"
    )


def _onvif_call(url, user, password, body):
    import requests

    data = _SOAP.format(security=_ws_security(user, password), body=body)
    r = requests.post(url, data=data.encode(), timeout=6,
                      headers={"Content-Type": "application/soap+xml; charset=utf-8"})
    r.raise_for_status()
    return r.text


def resolve_onvif(cam: dict) -> str:
    """Ask an ONVIF device for its stream URI (main = first profile, sub = second)."""
    host = cam.get("host")
    port = cam.get("port") or 80
    media = f"http://{host}:{port}/onvif/media_service"
    user, pwd = cam.get("username") or "", cam.get("password") or ""
    xml = _onvif_call(media, user, pwd, "<trt:GetProfiles/>")
    tokens = re.findall(r'Profiles[^>]*token="([^"]+)"', xml)
    if not tokens:
        raise RuntimeError("ONVIF: هیچ پروفایلی یافت نشد")
    token = tokens[1] if (cam.get("stream") == "sub" and len(tokens) > 1) else tokens[0]
    body = (
        "<trt:GetStreamUri><trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream>"
        "<tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport></trt:StreamSetup>"
        f"<trt:ProfileToken>{token}</trt:ProfileToken></trt:GetStreamUri>"
    )
    xml = _onvif_call(media, user, pwd, body)
    m = re.search(r"<(?:\w+:)?Uri>([^<]+)</(?:\w+:)?Uri>", xml)
    if not m:
        raise RuntimeError("ONVIF: آدرس استریم دریافت نشد")
    uri = m.group(1).replace("&amp;", "&")
    if user and "@" not in uri:
        uri = uri.replace("rtsp://", f"rtsp://{_auth(cam)}", 1)
    return uri


def mask_url(url: str) -> str:
    return re.sub(r"//([^:/@]+):([^@]+)@", r"//\1:****@", url or "")
