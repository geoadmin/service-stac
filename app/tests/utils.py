def mock_request_from_response(factory, response):
    '''Mock a request from a client response

    This can be used to verify a client response against the manually serialized response data.
    Some serializer require a request context in order to generate links.
    '''
    return factory.get(f'{response.request["PATH_INFO"]}?{response.request["QUERY_STRING"]}')


def get_http_error_description(json_response):
    '''Get the HTTP error description from response
    '''
    return f"{json_response['description'] if 'description' in json_response else ''}"
