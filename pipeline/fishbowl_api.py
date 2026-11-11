import base64
import hashlib
import json
import os
import socket
import struct
from dataclasses import dataclass


SUCCESS_CODES = {900, 1000}
AUTH_CODES = {1100, 1110, 1111, 1112, 1120, 1130, 1131, 1140, 1162, 1163, 1164}


class FishbowlApiError(Exception):
    def __init__(self, status_code: int, status_message: str = ""):
        self.status_code = status_code
        self.status_message = status_message
        text = f"Fishbowl API error {status_code}"
        if status_message:
            text = f"{text}: {status_message}"
        super().__init__(text)


class FishbowlAuthError(FishbowlApiError):
    pass


@dataclass
class FishbowlLoginResult:
    user_id: int | None
    full_name: str
    server_version: str
    ticket_key: str


def fishbowl_api_password(password: str) -> str:
    digest = hashlib.md5(password.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


class FishbowlApiClient:
    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        app_name: str = "fishbowl_automation_probe",
        app_description: str = "Fishbowl automation integration",
        app_id: int = 20261102,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.app_name = app_name
        self.app_description = app_description
        self.app_id = app_id
        self.ticket_key = ""
        self.user_id: int | None = None

    @classmethod
    def from_env(cls) -> "FishbowlApiClient":
        host = os.getenv("FISHBOWL_HOST") or os.getenv("DB_HOST", "localhost")
        port = int(os.getenv("FISHBOWL_PORT", "28192"))
        username = (os.getenv("FISHBOWL_USERNAME") or "").strip()
        password = (os.getenv("FISHBOWL_PASSWORD") or "").strip()
        if not username or not password:
            raise ValueError("Fishbowl credentials missing from environment")
        return cls(host=host, port=port, username=username, password=password)

    def login(self) -> FishbowlLoginResult:
        response = self._send_request(
            "LoginRq",
            {
                "IAName": self.app_name,
                "IADescription": self.app_description,
                "IAID": self.app_id,
                "UserName": self.username,
                "UserPassword": fishbowl_api_password(self.password),
            },
            ticket_key="",
        )
        outer_status, inner, ticket = self._unwrap(response, "LoginRs")
        status_code = inner.get("statusCode", outer_status)
        self._raise_for_status(status_code, inner.get("statusMessage", ""))
        self.ticket_key = ticket.get("Key", "") or ""
        self.user_id = ticket.get("UserID")
        return FishbowlLoginResult(
            user_id=self.user_id,
            full_name=inner.get("UserFullName", ""),
            server_version=inner.get("ServerVersion", ""),
            ticket_key=self.ticket_key,
        )

    def logout(self) -> None:
        if not self.ticket_key:
            return
        response = self._send_request("LogoutRq", {}, ticket_key=self.ticket_key)
        outer_status, inner, _ = self._unwrap(response, "LogoutRs")
        status_code = inner.get("statusCode", outer_status)
        if status_code not in SUCCESS_CODES and status_code != 1164:
            self._raise_for_status(status_code, inner.get("statusMessage", ""))
        self.ticket_key = ""
        self.user_id = None

    def get_import_list(self) -> list[str]:
        response = self._send_request("ImportListRq", {}, ticket_key=self.ticket_key)
        outer_status, inner, _ = self._unwrap(response, "ImportListRs")
        status_code = inner.get("statusCode", outer_status)
        self._raise_for_status(status_code, inner.get("statusMessage", ""))
        names = inner.get("ImportNames", {}).get("ImportName", [])
        return names if isinstance(names, list) else [names]

    def get_import_headers(self, import_type: str) -> list[str]:
        response = self._send_request("ImportHeaderRq", {"Type": import_type}, ticket_key=self.ticket_key)
        outer_status, inner, _ = self._unwrap(response, "ImportHeaderRs")
        status_code = inner.get("statusCode", outer_status)
        self._raise_for_status(status_code, inner.get("statusMessage", ""))
        rows = inner.get("Header", {}).get("Row", [])
        return rows if isinstance(rows, list) else [rows]

    def import_rows(self, import_type: str, rows: list[str]) -> None:
        response = self._send_request(
            "ImportRq",
            {"Type": import_type, "Rows": {"Row": rows}},
            ticket_key=self.ticket_key,
        )
        outer_status, inner, _ = self._unwrap(response, "ImportRs")
        status_code = inner.get("statusCode", outer_status)
        self._raise_for_status(status_code, inner.get("statusMessage", ""))

    def void_sales_order(self, so_number: str) -> None:
        response = self._send_request(
            "VoidSORq", {"SONumber": str(so_number)}, ticket_key=self.ticket_key
        )
        outer_status, inner, _ = self._unwrap(response, "VoidSORs")
        status_code = inner.get("statusCode", outer_status)
        self._raise_for_status(status_code, inner.get("statusMessage", ""))

    def _send_request(self, element_name: str, payload: dict, ticket_key: str) -> dict:
        request = {
            "FbiJson": {
                "Ticket": {"Key": ticket_key},
                "FbiMsgsRq": {element_name: payload},
            }
        }
        body = json.dumps(request, separators=(",", ":")).encode("ascii")
        with socket.create_connection((self.host, self.port), timeout=10) as sock:
            sock.settimeout(10)
            sock.sendall(struct.pack(">I", len(body)))
            sock.sendall(body)
            response_len = struct.unpack(">I", self._recv_exact(sock, 4))[0]
            response_body = self._recv_exact(sock, response_len)
        return json.loads(response_body.decode("ascii"))

    def _recv_exact(self, sock: socket.socket, size: int) -> bytes:
        data = bytearray()
        while len(data) < size:
            chunk = sock.recv(size - len(data))
            if not chunk:
                raise RuntimeError("socket closed before full response was received")
            data.extend(chunk)
        return bytes(data)

    def _unwrap(self, response: dict, response_name: str) -> tuple[int, dict, dict]:
        fbi_json = response.get("FbiJson", {})
        msgs = fbi_json.get("FbiMsgsRs", {})
        ticket = fbi_json.get("Ticket", {})
        return msgs.get("statusCode", 0), msgs.get(response_name, {}), ticket

    def _raise_for_status(self, status_code: int, status_message: str) -> None:
        if status_code in SUCCESS_CODES:
            return
        if status_code in AUTH_CODES:
            raise FishbowlAuthError(status_code, status_message)
        raise FishbowlApiError(status_code, status_message)
