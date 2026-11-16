import subprocess


def run_cmd(cmd):
    """
    运行系统命令，返回标准输出，标准错误输出及执行状态码
    :param cmd:
    :return:
    """
    p = subprocess.run(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    cmd_stdout = bytes.decode(p.stdout)
    if cmd_stdout.endswith('\n'):
        cmd_stdout = cmd_stdout.strip()
    # cmd_stderr = bytes.decode(p.stderr)

    if p.returncode == '0':
        return None
    else:
        # return cmd_stdout, cmd_stderr, p.returncode
        return cmd_stdout


def format_desc(quote, pro_help, pro_type="gauge"):
    return "# HELP {} {}.\n# TYPE {} {}\n".format(quote, pro_help, quote, pro_type)

