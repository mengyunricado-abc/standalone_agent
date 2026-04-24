def flatten_context(data):
    flat = {}
    if not isinstance(data, dict):
        return flat
        
    for k, v in data.items():
        if isinstance(v, dict):
            flat.update(v)
            flat[k] = v
        else:
            flat[k] = v
    return flat

test_data = {
    "application_form": {
        "software_name": "Test App",
        "dev_purpose": "Testing"
    },
    "design_doc": {
        "full_name": "Test App Full",
        "intro": "Hello"
    }
}

result = flatten_context(test_data)
print(f"Result keys: {list(result.keys())}")
print(f"software_name: {result.get('software_name')}")
print(f"full_name: {result.get('full_name')}")
assert result.get('software_name') == "Test App"
assert result.get('full_name') == "Test App Full"
print("Test passed!")
