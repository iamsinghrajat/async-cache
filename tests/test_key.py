import copy
from cache.key import _to_hashable, make_key

def dummy(a, b=None):
    return a, b


def test_list_contents_equal_are_same_key():
    l1 = [1, 2, 3]
    l2 = [1, 2, 3]  # different object, same contents

    name1, key1 = make_key(dummy, (l1,), {})
    name2, key2 = make_key(dummy, (l2,), {})

    assert name1 == name2
    assert key1 == key2
    assert hash(key1) == hash(key2)


def test_mutated_list_changes_key():
    l = [1]
    _, key_before = make_key(dummy, (l,), {})
    # mutate the same list object
    l.append(2)
    _, key_after = make_key(dummy, (l,), {})

    assert key_before != key_after
    # hashes must reflect inequality
    assert hash(key_before) != hash(key_after)


def test_number_vs_string_are_different_keys():
    _, key_num = make_key(dummy, (1,), {})
    _, key_num_again = make_key(dummy, (1,), {})
    _, key_str = make_key(dummy, ("1",), {})

    assert key_num == key_num_again
    assert key_num != key_str
    assert hash(key_num) == hash(key_num_again)
    assert hash(key_num) != hash(key_str)


def test_kwargs_order_does_not_affect_key():
    b1 = [42]
    b2 = [42]

    kw1 = {"a": 1, "b": b1}
    # different insertion order
    kw2 = {"b": b2, "a": 1}

    _, k1 = make_key(dummy, (), kw1)
    _, k2 = make_key(dummy, (), kw2)

    assert k1 == k2
    assert hash(k1) == hash(k2)


def test_unordered_collections_like_sets_treated_by_value():
    s1 = {1, 2, 3}
    s2 = {3, 2, 1}

    _, k1 = make_key(dummy, (s1,), {})
    _, k2 = make_key(dummy, (s2,), {})

    assert k1 == k2
    assert hash(k1) == hash(k2)


def test_nested_structures_and_multiple_args():
    arg1_a = {"x": [1, 2], "y": (3, 4)}
    arg1_b = {"y": (3, 4), "x": [1, 2]}  # same content, different order in dict
    arg2 = [9, 8]

    _, k1 = make_key(dummy, (arg1_a, arg2), {})
    _, k2 = make_key(dummy, (arg1_b, arg2), {})

    assert k1 == k2
    assert hash(k1) == hash(k2)


def test_object_with_dicts_are_compared_by_value():
    class C:
        def __init__(self, x, y):
            self.x = x
            self.y = y

    a = C(1, [2, 3])
    b = C(1, [2, 3])  # different instance, same contents

    _, ka = make_key(dummy, (a,), {})
    _, kb = make_key(dummy, (b,), {})

    assert ka == kb
    assert hash(ka) == hash(kb)

def test_object_type_distinction():
    class A:
        def __init__(self, x):
            self.x = x

    class B:
        def __init__(self, x):
            self.x = x

    _, k1 = make_key(dummy, (A(1),), {})
    _, k2 = make_key(dummy, (B(1),), {})

    assert k1 != k2

def test_kwargs_order_independent():
    _, k1 = make_key(dummy, (), {"a": 1, "b": 2})
    _, k2 = make_key(dummy, (), {"b": 2, "a": 1})

    assert k1 == k2

def test_deep_complex_structure():
    data = {
        "a": [1, 2, {"b": {3, 4}}],
        "c": (5, 6),
    }

    _, k1 = make_key(dummy, (data,), {})
    _, k2 = make_key(dummy, (data,), {})

    assert k1 == k2

def test_use_cache_removed():
    _, k1 = make_key(dummy, (), {"a": 1, "use_cache": True})
    _, k2 = make_key(dummy, (), {"a": 1})

    assert k1 == k2

def test_function_name_affects_key():
    def f(): pass
    def g(): pass

    k1 = make_key(f, (), {})
    k2 = make_key(g, (), {})

    assert k1 != k2

def test_skip_args():
    class Obj:
        pass

    self1 = Obj()
    self2 = Obj()

    _, k1 = make_key(dummy, (self1, 1), {}, skip_args=1)
    _, k2 = make_key(dummy, (self2, 1), {}, skip_args=1)

    assert k1 == k2

def test_int_vs_str_not_equal():
    _, k1 = make_key(dummy, (1,), {})
    _, k2 = make_key(dummy, ("1",), {})

    assert k1 != k2

def test_set_order_independent():
    _, k1 = make_key(dummy, ({1, 2, 3},), {})
    _, k2 = make_key(dummy, ({3, 2, 1},), {})

    assert k1 == k2

def test_nested_structures_equal():
    a = {"x": [1, {"y": 2}]}
    b = {"x": [1, {"y": 2}]}

    _, k1 = make_key(dummy, (a,), {})
    _, k2 = make_key(dummy, (b,), {})

    assert k1 == k2

def test_list_args_are_equal():
    _, k1 = make_key(dummy, ([1, 2, 3],), {})
    _, k2 = make_key(dummy, ([1, 2, 3],), {})

    assert k1 == k2
    assert hash(k1) == hash(k2)


def test_make_key_skip_args_and_use_cache_copy_behavior():
    # test skip_args
    class Dummy:
        def method(self, x):
            return x

    obj = Dummy()
    args = (obj, 7, "ignored")
    original_kwargs = {"use_cache": False, "foo": "bar"}
    kwargs_copy = copy.deepcopy(original_kwargs)

    name, key = make_key(Dummy.method, args, original_kwargs, skip_args=1)
    # func name should be taken from qualname
    assert isinstance(name, str)
    # ensure 'use_cache' was removed in internal KEY but original dict unchanged
    assert "use_cache" in original_kwargs
    assert original_kwargs == kwargs_copy  # make_key must not mutate caller's dict

    # ensure KEY was built from args after skipping first ('self')
    assert key.args and key.args[0] == _to_hashable(7)


def test_key_hash_eq_contract_and_repr():
    a = [1, 2]
    b = [1, 2]
    _, k1 = make_key(dummy, (a,), {"z": 10})
    _, k2 = make_key(dummy, (b,), {"z": 10})

    assert k1 == k2
    assert hash(k1) == hash(k2)
    # __repr__ returns a string and contains class name
    r = repr(k1)
    assert "KEY" in r and "args=" in r and "kwargs=" in r