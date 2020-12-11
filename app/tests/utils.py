import json
import os

from django.conf import settings

TESTDATADIR = settings.BASE_DIR / 'app/tests/sample_data_test/'


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


def get_sample_data(topic):
    '''Get a dictionary of sample data as json

    This function takes a string describing the subpath to the sample data and returns a
    dictionary with key = filename, value = json.

    f.ex. get_sample_data('collections')
    Args:
        topic: the name of the topic (f.ex. collections).
    Returns:
         dict mapping keys to corresponding json object.
         For example:
            {'invalid_collection_set_1': json object }
    '''
    path_to_json = f"{TESTDATADIR}/{topic}"
    json_files = [pos_json for pos_json in os.listdir(path_to_json) if pos_json.endswith('.json')]
    dict_sampled_topic = {}
    for name_json_file in json_files:
        with open(os.path.join(path_to_json, name_json_file)) as json_file:
            dict_sampled_topic[name_json_file.split('.')[0]] = json.load(json_file)
    return dict_sampled_topic
