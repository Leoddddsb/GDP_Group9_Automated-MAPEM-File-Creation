class Transformer:
    @classmethod
    def from_crs(cls, *_args, **_kwargs):
        return cls()

    def transform(self, x, y):
        return x, y
