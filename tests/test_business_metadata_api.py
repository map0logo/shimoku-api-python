""""""
from os import getenv
from typing import Dict, List
import unittest

import shimoku_api_python as shimoku
from shimoku_api_python import Client


api_key: str = getenv('API_TOKEN')
universe_id: str = getenv('UNIVERSE_ID')
business_id: str = getenv('BUSINESS_ID')


config = {
    'access_token': api_key,
}

s = shimoku.Client(
    config=config,
    universe_id=universe_id,
)


def test_get_business():
    result = s.business.get_business(business_id)
    print(result)


def test_get_fake_business():
    class MyTestCase(unittest.TestCase):
        def test_fake_business(self):
            with self.assertRaises(ApiClientError):
                business_id_: str = 'this is a test'
                s.business.get_business(
                    business_id=business_id_,
                )

    t = MyTestCase()
    t.test_fake_business()


def test_create_and_delete_business():
    business: Dict = s.business.create_business(name='auto-test')
    business_id_: str = business['id']

    assert len(business_id_) > 0

    business_from_db: Dict = (
        s.business.get_business(
            business_id=business_id_,
        )
    )

    assert business_from_db == business
    del business_from_db

    result: Dict = (
        s.business.delete_business(
            business_id=business_id_,
        )
    )

    assert result


def test_update_business():
    business_original: Dict = (
        s.business.get_business(business_id)
    )
    business_name: str = business_original['name']
    new_business_name: str = f'{business_name}_changed'

    new_business: Dict = (
        s.business.update_business(
            business_id=business_id,
            business_data={'name': new_business_name},
        )
    )

    business_changed: Dict = s.business.get_business(business_id)
    assert new_business == business_changed
    assert new_business_name == business_changed['name']

    # Restore previous name
    _ = (
        s.business.update_business(
            business_id=business_id,
            business_data={'name': business_name},
        )
    )
    business_restored: Dict = s.business.get_business(business_id)
    assert business_name == business_restored['name']


def test_rename_business():
    business_original: Dict = (
        s.business.get_business(business_id)
    )
    business_name: str = business_original['name']
    new_business_name: str = f'{business_name}_changed'

    new_business: Dict = (
        s.business.rename_business(
            business_id=business_id,
            new_name=new_business_name,
        )
    )

    business_changed: Dict = s.business.get_business(business_id)
    assert new_business == business_changed
    assert new_business_name == business_changed['name']

    # Restore previous name
    _ = (
        s.business.rename_business(
            business_id=business_id,
            new_name=business_name,
        )
    )
    business_restored: Dict = s.business.get_business(business_id)
    assert business_name == business_restored['name']


test_get_business()
test_get_fake_business()
test_create_and_delete_business()
test_update_business()
test_rename_business()
