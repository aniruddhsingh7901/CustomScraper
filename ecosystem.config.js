module.exports = {
  apps: [
    {
      name: "dd-fetcher",
      cwd: "/root/data-universe",
      // Run a persistent bash loop that executes the Python fetcher every 30 minutes
      script: "/bin/bash",
      args: [
        "-lc",
        "while true; do /root/data-universe/.venv/bin/python scripts/fetch_dynamic_desirability.py --wallet.name An-13 --wallet.hotkey An-1 --subtensor.network finney --netuid 13 --vpermit_rao_limit 10000 || true; sleep 1800; done"
      ],
      autorestart: true,
      watch: false,
      time: true,
      env: {
        PYTHONUNBUFFERED: "1"
      }
    }
  ]
};
