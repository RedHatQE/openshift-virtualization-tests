from utilities.bitwarden import get_cnv_tests_secret_by_name

if __name__ == "__main__":
    print(get_cnv_tests_secret_by_name(secret_name="os_login")["fedora"]["password"])
