"""Competition policy; historical versions remain readable."""

CPP_ONLY = "参赛和提交 Bot 仅支持 C++17；请上传 .cpp、.cc、.cxx 或包含 C++ 源码的 ZIP。"
BUILTIN_VERSIONS = {"builtin-baseline-v1", "builtin-raider-v1"}


def trusted_builtin(version):
    return (
        version["id"] in BUILTIN_VERSIONS
        and bool(version["builtin"])
        and version["owner_id"] is None
    )


def eligible(version):
    return version["language"] == "cpp" or trusted_builtin(version)
