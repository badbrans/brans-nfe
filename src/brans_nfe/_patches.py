from nfelib.nfse.bindings.v1_0 import tipos_simples_v1_00 as ts


def _completar_enum_ret_piscofins() -> None:
    enum_cls = ts.TstipoRetPiscofins
    for digit in range(10):
        name = f"VALUE_{digit}"
        value = str(digit)
        if name in enum_cls._member_map_:
            continue
        new_member = object.__new__(enum_cls)
        new_member._name_ = name
        new_member._value_ = value
        enum_cls._member_map_[name] = new_member
        enum_cls._value2member_map_[value] = new_member
        if name not in enum_cls._member_names_:
            enum_cls._member_names_.append(name)
        type.__setattr__(enum_cls, name, new_member)


def aplicar_patches() -> None:
    _completar_enum_ret_piscofins()
