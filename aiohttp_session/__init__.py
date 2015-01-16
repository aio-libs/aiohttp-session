from collections import MutableMapping


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
