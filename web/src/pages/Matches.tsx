import { Plus } from "@nsmr/pixelart-react";
import type { User } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { PageHead } from "@/components/pixel";
import MatchBrowser from "@/components/MatchBrowser";

export default function Matches({ user }: { user: User | null }) {
  return (
    <>
      <PageHead
        eyebrow="对战记录"
        title="每一局都能回放"
        description="全站的公开对局，以及你自己的私人对局。某场比赛的对局也可以在比赛页的“对局”里看。"
        action={
          user && (
            <Button asChild>
              <a href="/tests?new=1">
                <Plus size={16} /> 新建私人对练
              </a>
            </Button>
          )
        }
      />
      <MatchBrowser user={user} />
    </>
  );
}
