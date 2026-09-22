import unittest

from backend.app.services.amap_service import AmapService


class AmapServiceTest(unittest.TestCase):
    def test_extract_route_path_orders_and_deduplicates_polyline_points(self):
        route = {
            "steps": [
                {"polyline": "116.1,39.1;116.2,39.2"},
                {"polyline": "116.2,39.2;116.3,39.3"},
            ]
        }

        path = AmapService._extract_route_path(route)

        self.assertEqual([(point.longitude, point.latitude) for point in path], [
            (116.1, 39.1),
            (116.2, 39.2),
            (116.3, 39.3),
        ])


if __name__ == "__main__":
    unittest.main()
