import { defineRailway, github, postgres, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const Postgres = postgres("Postgres", { region: "sfo" });
  Postgres.networking = { privateNetworkEndpoint: "postgres" };
  Postgres.deploy = { ...Postgres.deploy, ipv6EgressEnabled: true };
  const postgresVolume = volume("postgres-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "sfo", sizeMB: 500 });
  const message_app = service("message_app", {
    source: github("bnfarrell/message_app", { checkSuites: false, rootDirectory: "/" }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    healthcheck: "/api/health",
    healthcheckTimeout: 60,
    replicas: { "sfo": 1 },
    deploy: { restartPolicyMaxRetries: 3 },
    networking: { privateNetworkEndpoint: "messageapp" },
    env: { ALLOW_TEST_EMAIL_DOMAINS: preserve(), DATABASE_URL: preserve(), PUBLIC_BASE_URL: preserve(), SESSION_SECRET: preserve(), SMS_ADAPTER: preserve(), TWILIO_ACCOUNT_SID: preserve(), TWILIO_AUTH_TOKEN: preserve() },
  });

  return project("message_app", {
    resources: [Postgres, message_app, postgresVolume],
  });
});
