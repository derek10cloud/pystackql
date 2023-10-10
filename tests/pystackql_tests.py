import json, os, sys, platform, re, time, unittest, subprocess
import pandas as pd
from termcolor import colored
import unittest.mock as mock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from pystackql import StackQL
from pystackql.stackql_magic import StackqlMagic, load_ipython_extension

server_port = 5466

expected_properties = [
    "bin_path", "download_dir", "package_version", "params", 
    "parse_json", "platform", "server_mode", "sha", "version"
]

expected_version_pattern = r'^v?(\d+\.\d+\.\d+)$'  # should be 'vN.N.N' or 'N.N.N'

expected_platform_pattern = r'^(Windows|Linux|Darwin) (\w+) \(([^)]+)\), Python (\d+\.\d+\.\d+)$'

custom_windows_download_dir = 'C:\\temp'
custom_mac_linux_download_dir = '/tmp'

registry_pull_google_query = "REGISTRY PULL google"
registry_pull_aws_query = "REGISTRY PULL aws"

def registry_pull_resp_pattern(provider):
    return r"%s provider, version 'v\d+\.\d+\.\d+' successfully installed" % provider

google_query = f"""
SELECT status, count(*) as num_instances
FROM google.compute.instances
WHERE project = '{os.environ['GCP_PROJECT']}' 
AND zone = '{os.environ['GCP_ZONE']}'
GROUP BY status
"""

regions = os.environ.get('REGIONS').split(',')

async_queries = [
    f"""
    SELECT '{region}' as region, instanceType, COUNT(*) as num_instances
    FROM aws.ec2.instances
    WHERE region = '{region}'
    GROUP BY instanceType
    """
    for region in regions
]

def pystackql_test_setup(func):
    def wrapper(self):
        try:
            del self.stackql
        except AttributeError:
            pass
        self.stackql = StackQL()
        func(self)
    return wrapper

server_mode_header = colored("[SERVER MODE]", 'yellow')
ipython_mode_header = colored("[MAGIC EXT]", 'blue')

def print_test_result(test_name, condition, server_mode=False, is_ipython=False):
    status_header = colored("[PASSED] ", 'green') if condition else colored("[FAILED] ", 'red')
    headers = [status_header]

    if server_mode:
        headers.append(server_mode_header)
    
    if is_ipython:
        headers.append(ipython_mode_header)

    headers.append(test_name)

    message = " ".join(headers)
    print("\n" + message)

class PyStackQLTestsBase(unittest.TestCase):
    pass

def setUpModule():
    print("downloading stackql binary...")
    PyStackQLTestsBase.stackql = StackQL()
    print("starting stackql server...")
    PyStackQLTestsBase.server_process = subprocess.Popen([PyStackQLTestsBase.stackql.bin_path, "srv", "--pgsrv.port", str(server_port)])
    time.sleep(5)

def tearDownModule():
    print("stopping stackql server...")
    if PyStackQLTestsBase.server_process:
        PyStackQLTestsBase.server_process.terminate()
        PyStackQLTestsBase.server_process.wait()

class PyStackQLNonServerModeTests(PyStackQLTestsBase):

    @pystackql_test_setup
    def test_01_properties_class_method(self):
        properties = self.stackql.properties()
        
        # Check that properties is a dictionary
        self.assertTrue(isinstance(properties, dict), "properties should be a dictionary")
        
        # List of keys we expect to be in the properties
        missing_keys = [key for key in expected_properties if key not in properties]
        self.assertTrue(len(missing_keys) == 0, f"Missing keys in properties: {', '.join(missing_keys)}")

        # Further type checks (as examples)
        self.assertIsInstance(properties["bin_path"], str, "bin_path should be of type str")
        self.assertIsInstance(properties["params"], list, "params should be of type list")
        self.assertIsInstance(properties["parse_json"], bool, "parse_json should be of type bool")

        # If all the assertions pass, then the properties are considered valid.
        print_test_result("Test properties method", True)

    @pystackql_test_setup
    def test_02_version_attribute(self):
        version = self.stackql.version
        self.assertIsNotNone(version)
        is_valid_semver = bool(re.match(expected_version_pattern, version))
        self.assertTrue(is_valid_semver)
        print_test_result("Test version attribute", is_valid_semver)

    @pystackql_test_setup
    def test_03_platform_attribute(self):
        platform_string = self.stackql.platform
        self.assertIsNotNone(platform_string)
        
        is_valid_platform = bool(re.match(expected_platform_pattern, platform_string))
        self.assertTrue(is_valid_platform)
        print_test_result("Test platform attribute", is_valid_platform)

    @pystackql_test_setup
    def test_04_bin_path_attribute(self):
        self.assertTrue(os.path.exists(self.stackql.bin_path))
        print_test_result("Test bin_path attribute with default download path", os.path.exists(self.stackql.bin_path))

    @pystackql_test_setup
    def test_05_set_custom_download_dir(self):
        this_platform = platform.system().lower()
        if this_platform == "windows":
            download_dir = custom_windows_download_dir
        else:
            download_dir = custom_mac_linux_download_dir
        self.stackql = StackQL(download_dir=download_dir)
        version = self.stackql.version
        self.assertIsNotNone(version)
        print_test_result("Test setting a custom download_dir", version is not None)

    @pystackql_test_setup
    def test_06_custom_params_and_table_output(self):
        self.stackql = StackQL(output="table")
        self.assertIn("table", self.stackql.params)
        self.assertFalse(self.stackql.parse_json)
        print_test_result("Test setting table output", not self.stackql.parse_json)

    @pystackql_test_setup
    def test_07_executeStmt(self):
        
        result = self.stackql.executeStmt(registry_pull_google_query)
        expected_pattern = registry_pull_resp_pattern("google")
        self.assertTrue(re.search(expected_pattern, result), f"Expected pattern not found in result: {result}")
        
        result = self.stackql.executeStmt(registry_pull_aws_query)
        expected_pattern = registry_pull_resp_pattern("aws")
        self.assertTrue(re.search(expected_pattern, result), f"Expected pattern not found in result: {result}")

        print_test_result("Test executeStmt method", True)

    @pystackql_test_setup
    def test_08_execute(self):
        result = self.stackql.execute(google_query)
        
        # Convert the result to a pandas dataframe
        df = pd.DataFrame(result)

        # Assert the dataframe structure
        self.assertTrue('num_instances' in df.columns and 'status' in df.columns, "Columns 'num_instances' and 'status' should exist in the DataFrame")
        self.assertTrue(len(df) >= 1, "DataFrame should have one or more rows")
        
        print_test_result("Test execute method", True)

    @pystackql_test_setup
    def test_09_executeQueriesAsync(self):
        results = self.stackql.executeQueriesAsync(async_queries)

        # Convert the results to a pandas DataFrame
        df = pd.DataFrame(results)

        # Check that the DataFrame has the required columns
        self.assertTrue('region' in df.columns, "'region' column missing in DataFrame")
        self.assertTrue('instanceType' in df.columns, "'instanceType' column missing in DataFrame")
        self.assertTrue('num_instances' in df.columns, "'num_instances' column missing in DataFrame")

        # Check that all regions are represented in the DataFrame
        unique_regions_in_df = df['region'].unique()
        for region in regions:
            self.assertTrue(region in unique_regions_in_df, f"Region '{region}' not found in DataFrame")

        print_test_result("Test executeQueriesAsync method", True)

class PyStackQLServerModeTests(PyStackQLTestsBase):

    @pystackql_test_setup
    def test_10_server_mode_connectivity(self):
        self.stackql = StackQL(server_mode=True, server_port=server_port)
        self.assertTrue(self.stackql.server_mode, "StackQL should be in server mode")
        self.assertIsNotNone(self.stackql._conn, "Connection object should not be None")
        print_test_result("Test server mode connectivity", True, True)

    @pystackql_test_setup
    def test_11_executeStmt_server_mode(self):
        self.stackql = StackQL(server_mode=True, server_port=server_port)
        result = self.stackql.executeStmt(registry_pull_google_query)
        self.assertEqual(result, "[]", f"Expected empty list, got: {result}")
        print_test_result("Test executeStmt in server mode", True, True)

    @pystackql_test_setup
    def test_12_execute_server_mode_to_pandas(self):
        self.stackql = StackQL(server_mode=True, server_port=server_port)
        result = self.stackql.execute(google_query)

        # If the result is a list of dictionaries, then proceed to convert to DataFrame
        if isinstance(result, list) and len(result) > 0 and isinstance(result[0], dict):
            df = pd.DataFrame(result)
            
            # Continue with your assertions
            self.assertTrue('num_instances' in df.columns and 'status' in df.columns, "Columns 'num_instances' and 'status' should exist in the DataFrame")
            self.assertTrue(len(df) >= 1, "DataFrame should have one or more rows")
            print_test_result("Test execute method in server mode", True, True)
        else:
            self.fail(f"Unexpected result format: {result}")

class MockInteractiveShell:
    """A mock class for IPython's InteractiveShell."""
    user_ns = {}  # Mock user namespace

    def register_magics(self, magics):
        """Mock method to 'register' magics."""
        self.magics = magics

    @staticmethod
    def instance():
        """Return a mock instance of the shell."""
        return MockInteractiveShell()

class StackQLMagicTests(PyStackQLTestsBase):

    def setUp(self):
        """Set up for the magic tests."""
        self.shell = MockInteractiveShell.instance()
        load_ipython_extension(self.shell)
        self.stackql_magic = StackqlMagic(shell=self.shell)

    def test_14_magic_cell_query(self):
        # Test the cell magic functionality
        df = self.stackql_magic.stackql("", google_query)  # Cell magic uses both line and cell arguments
        self.assertTrue(isinstance(df, pd.DataFrame))
        self.assertTrue('num_instances' in df.columns and 'status' in df.columns)
        print_test_result("test cell magic", True, True, True)

    def test_15_magic_cell_query_no_display(self):
        # Test the cell magic functionality with the --no-display option
        df = self.stackql_magic.stackql("--no-display", google_query)
        self.assertIsNone(df)
        print_test_result("test cell magic with --no-display", True, True, True)

def main():
    unittest.main()

if __name__ == '__main__':
    main()
