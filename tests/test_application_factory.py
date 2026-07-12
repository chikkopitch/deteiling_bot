from app.main import create_dispatcher


def test_dispatcher_contains_root_router() -> None:
    dispatcher = create_dispatcher()

    assert dispatcher.sub_routers
    assert dispatcher.sub_routers[0].name == "root"
