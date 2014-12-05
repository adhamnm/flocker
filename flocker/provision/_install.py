from fabric.api import run, execute, env, put
from pipes import quote as shell_quote
from cStringIO import StringIO
import posixpath
from textwrap import dedent
from urlparse import urljoin

ZFS_REPO = ("https://s3.amazonaws.com/archive.zfsonlinux.org/"
            "fedora/zfs-release$(rpm -E %dist).noarch.rpm")
CLUSTERHQ_REPO = ("https://storage.googleapis.com/archive.clusterhq.com/"
                  "fedora/clusterhq-release$(rpm -E %dist).noarch.rpm")


def _task_install_kernel():
    run("""
UNAME_R=$(uname -r)
PV=${UNAME_R%.*}
KV=${PV%%-*}
SV=${PV##*-}
ARCH=$(uname -m)
yum install -y https://kojipkgs.fedoraproject.org/packages/kernel/\
${KV}/${SV}/${ARCH}/kernel-devel-${UNAME_R}.rpm
""")


def _task_enable_docker():
    run("systemctl enable docker.service")
    run("systemctl start docker.service")


def _task_disable_firewall():
    run('firewall-cmd --permanent --direct --add-rule ipv4 filter FORWARD 0 -j ACCEPT')  # noqa
    run('firewall-cmd --direct --add-rule ipv4 filter FORWARD 0 -j ACCEPT')


def _task_create_flocker_pool_file():
    run('mkdir /opt/flocker')
    run('truncate --size 1G /opt/flocker/pool-vdev')
    run('zpool create flocker /opt/flocker/pool-vdev')


def _task_install_flocker(
        version=None, branch=None, distribution=None):
    run("yum install -y " + ZFS_REPO)
    run("yum install -y " + CLUSTERHQ_REPO)

    build_server = 'http://build.clusterhq.com/'  # FIXME
    if branch:
        result_path = posixpath.join(
            '/results/omnibus/', branch, distribution)
        base_url = urljoin(build_server, result_path)
        repo = dedent(b"""
            [clusterhq-build]
            name=clusterhq-build
            baseurl=%s
            gpgcheck=0
            enabled=0
            """) % (base_url,)
        put(StringIO(repo), '/etc/yum.repos.d/clusterhq-build.repo')
        branch_opt = ['--enablerepo=clusterhq-build']
    else:
        branch_opt = []

    if version:
        from admin.release import make_rpm_version  # FIXME
        rpm_version = "%s-%s" % make_rpm_version(version)
        if rpm_version.endswith('.dirty'):
            rpm_version = rpm_version[:-len('.dirty')]
        package = 'clusterhq-flocker-node-%s' % (rpm_version,)
    else:
        package = 'clusterhq-flocker-node'

    command = ["yum", "install"] + branch_opt + ["-y", package]
    run(" ".join(map(shell_quote, command)))


def _task_install():
    _task_install_kernel()
    _task_install_flocker()
    _task_enable_docker()
    _task_disable_firewall()
    _task_create_flocker_pool_file()


def install(nodes, username, version, kwargs):
    env.connection_attempts = 24
    env.timeout = 5
    env.pty = False
    execute(
        task=_task_install,
        hosts=["%s@%s" % (username, address) for address in nodes],
        **kwargs
    )
    from fabric.network import disconnect_all
    disconnect_all()
