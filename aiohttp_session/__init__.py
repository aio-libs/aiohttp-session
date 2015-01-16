from collections import MutableMapping
import time
import hmac
import hashlib


class Session(MutableMapping):
    """Session dict-like object.
    """

    def __init__(self, *, data=None, identity=None):
        self._changed = False
        self._mapping = {}
        self._identity = identity
        if data is not None:
            self._mapping.update(data)

    def __repr__(self):
        return '<{} [new:{}, changed:{}] {!r}>'.format(
            self.__class__.__name__, self.new, self._changed,
            self._mapping)

    @property
    def new(self):
        return self._identity is None

    @property
    def identity(self):
        return self._identity

    def changed(self):
        self._changed = True

    def invalidate(self):
        self._changed = True
        self._mapping = {}

    def __len__(self):
        return len(self._mapping)

    def __iter__(self):
        return iter(self._mapping)

    def __contains__(self, key):
        return key in self._mapping

    def __getitem__(self, key):
        return self._mapping[key]

    def __setitem__(self, key, value):
        self._mapping[key] = value
        self._changed = True

    def __delitem__(self, key):
        del self._mapping[key]
        self._changed = True


SESSION_KEY = 'aiohttp_session'


def get_session(request):
    ret = request.get(SESSION_KEY)
    if ret is None:
        raise RuntimeError(
            "Install aiohttp_session middleware "
            "in your aiohttp.web.Application")
    return ret


class SessionMiddleware:

    def __init__(self, secret_key, cookie_name, *,
                 session_max_age=None, domain=None, max_age=None, path=None,
                 secure=None, httponly=None):
        if isinstance(secret_key, str):
            secret_key = secret_key.encode('utf-8')
        self._secret_key = secret_key
        self._cookie_name = cookie_name
        self._cookie_params = dict(domain=domain,
                                   max_age=max_age,
                                   path=path,
                                   secure=secure,
                                   httponly=httponly)
        self.session_max_age = session_max_age

    def get_session_id(self, request):
        name = self._cookie_name
        raw_value = request.cookies.get(name)
        return self._decode_cookie(raw_value)

    def put_session_id(self, request, cookie_value):
        if cookie_value is None:
            request.response.del_cookie(self._cookie_name)
        else:
            raw_value = self._encode_cookie(cookie_value)
            request.response.set_cookie(self._cookie_name, raw_value,
                                        **self._cookie_params)

    def _encode_cookie(self, value):
        """Encode and sign cookie value.

        value argument must be str instance.
        """
        assert isinstance(value, str)
        name = self._cookie_name
        timestamp = str(int(time.time()))
        singature = self._get_signature(name, value, timestamp)
        return '|'.join((value, timestamp, singature))

    def _decode_cookie(self, value):
        """Decode and verify cookie value.

        value argument must be str.
        Returns decoded bytes value of cookie
        or None if value could not be decoded or verified.
        """
        if not value:
            return None
        parts = value.split('|')
        if len(parts) != 3:
            return None
        name = self._cookie_name
        value, timestamp, sign = parts

        if self.session_max_age is not None:
            if int(timestamp) < int(time.time()) - self.session_max_age:
                return None

        expected_sign = self._get_signature(name, value, timestamp)
        if not hmac.compare_digest(expected_sign, sign):
            # TODO: log warning
            return None
        return value

    def _get_signature(self, *parts):
        sign = hmac.new(self._secret_key, digestmod=hashlib.sha1)
        sign.update(('|'.join(parts)).encode('utf-8'))
        return sign.hexdigest()
