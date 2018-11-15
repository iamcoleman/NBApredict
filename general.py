"""General functions for the project"""


def set_type(values):
    test_val = values[0]  # Is there a better method than taking a test val?
    if is_int(test_val):
        return _set_type(values, int)
    elif is_float(test_val):
        return _set_type(values, float)
    else:
        values = [x if len(x) > 0 else None for x in values]  # Set empty strings to None
        return values


def get_type(values):
    """Returns the type of the values in a list where type is defined as the modal type in the list"""
    val_types = []
    for i in values:
        if isinstance(i, int):
            val_types.append("integer")
        elif isinstance(i, float):
            val_types.append("float")
        else:
            val_types.append("string")
    return max(set(val_types), key=val_types.count)  # The max, set, and key combo returns the modal type


def is_int(x):
    try:
        int(x)  # Will raise ValueError if '.2'; will not raise error if .2
        return True
    except ValueError:
        return False


def is_float(x):
    try:
        float(x)
        return True
    except ValueError:
        return False


def _set_type(values, new_type):
    new_vals = []
    for i in values:
        # print("value({}) is being set to type({})".format(i, new_type))
        if len(i) > 0:  # Some values may have len(0); we convert them to None to put into sql db
            new_vals.append(new_type(i))
        else:
            new_vals.append(None)
    return new_vals
