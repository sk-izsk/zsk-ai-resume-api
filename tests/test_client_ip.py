import base64
import hashlib
import hmac
import json
import time
import unittest

from starlette.requests import Request

from app.client_ip import client_ip, is_signed_by_netlify

SECRET = "proxy-secret"


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def netlify_token(secret=SECRET, iss="netlify", exp=None) -> str:
    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    claims = {"iss": iss, "exp": exp or time.time() + 60}
    payload = b64(json.dumps(claims).encode())
    signature = hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{b64(signature)}"


def request(**headers) -> Request:
    raw = [(name.replace("_", "-").encode(), value.encode()) for name, value in headers.items()]
    return Request({"type": "http", "headers": raw, "client": ("10.0.0.1", 1234)})


class ClientIpTest(unittest.TestCase):
    def test_ignores_a_forged_forwarded_for(self):
        ip = client_ip(request(x_forwarded_for="1.2.3.4", cf_connecting_ip="203.0.113.7"), SECRET)

        self.assertEqual(ip, "203.0.113.7")

    def test_trusts_netlify_header_only_when_signed(self):
        signed = request(x_nf_client_connection_ip="198.51.100.9", x_nf_sign=netlify_token(), cf_connecting_ip="netlify")
        forged = request(x_nf_client_connection_ip="198.51.100.9", x_nf_sign=netlify_token("wrong"), cf_connecting_ip="203.0.113.7")

        self.assertEqual(client_ip(signed, SECRET), "198.51.100.9")
        self.assertEqual(client_ip(forged, SECRET), "203.0.113.7")

    def test_rejects_expired_or_foreign_tokens(self):
        self.assertFalse(is_signed_by_netlify(netlify_token(exp=time.time() - 1), SECRET))
        self.assertFalse(is_signed_by_netlify(netlify_token(iss="someone"), SECRET))
        self.assertFalse(is_signed_by_netlify("not.a.token", SECRET))

    def test_falls_back_to_the_socket_address_locally(self):
        self.assertEqual(client_ip(request(), None), "10.0.0.1")


if __name__ == "__main__":
    unittest.main()
