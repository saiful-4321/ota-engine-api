import sys
import importlib
import traceback

def get_controllers(version: str):
    base_path = f"app.controllers.{version}."
    modules = [
        "AuthController",
        "DashboardController",
        "UserController",
        "SystemController",
        "IpWhitelistController",
        "PermissionController",
        "PublicController",
        "ReportController",
        "ExportController",
        "IDMController",
        "SabreController",
        "SearchController"
    ]

    if "ota_api" not in sys.path:
        sys.path.append("/Users/dev/Developer/SkyNovia/ota-engine-api/ota_api")  # Adjust path accordingly

    controllers = {}
    for module in modules:
        try:
            controllers[module] = importlib.import_module(base_path + module)
        except ModuleNotFoundError as e:
            print(f"❌ Module Not Found: {base_path}{module} → {e}")
        except Exception as e:
            print(f"⚠️ Import Error in {base_path}{module}: {e}")
            print(traceback.format_exc())  # Print full error traceback

    return controllers
