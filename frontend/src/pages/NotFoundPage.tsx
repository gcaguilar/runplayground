import { Link } from "@tanstack/react-router";
import { Compass } from "lucide-react";

import { Card, EmptyState } from "@/components/ui";
import { useI18n } from "@/i18n";

export function NotFoundPage() {
  const { t } = useI18n();
  return (
    <div className="not-found">
      <Card className="panel">
        <EmptyState
          icon={Compass}
          title={t("notFound.title")}
          description={t("notFound.desc")}
          action={
            <Link to="/" className="button button--primary button--md">
              {t("notFound.home")}
            </Link>
          }
        />
      </Card>
    </div>
  );
}
