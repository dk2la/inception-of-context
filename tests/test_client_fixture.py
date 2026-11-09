import os

from p1 import index


def test_client_talks_to_an_indexed_temporary_copy_of_the_target(client, temp_index):
    assert client.get("/status").status_code == 200
    assert os.path.exists(os.path.join(temp_index, "calculator", "core.py"))
    assert index.get_collection().count() > 0


def test_tests_do_not_share_a_target_project(client, temp_index):
    with open(os.path.join(temp_index, "only_here.py"), "w") as f:
        f.write("x = 1\n")


def test_the_file_from_the_previous_test_is_gone(client, temp_index):
    assert not os.path.exists(os.path.join(temp_index, "only_here.py"))
