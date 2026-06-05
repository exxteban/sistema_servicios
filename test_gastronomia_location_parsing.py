from gastronomia.services.pedido_service import _coords_from_location_text


def test_google_place_url_prefers_exact_place_coords_over_viewport_center():
    url = (
        'https://www.google.com/maps/place/Hipermercado+Luisito+-+San+Lorenzo/'
        '@-25.3696574,-57.5542708,15z/data=!4m6!3m5!1s0x945dad3232f58e91:'
        '0x23188e8785efa023!8m2!3d-25.3641298!4d-57.5308095!16s%2Fg%2F11vdn9v6jb'
    )

    assert _coords_from_location_text(url) == (-25.3641298, -57.5308095)


def test_google_place_url_without_exact_coords_uses_viewport_center():
    url = 'https://www.google.com/maps/place/test/@-25.3001,-57.6359,17z'

    assert _coords_from_location_text(url) == (-25.3001, -57.6359)
