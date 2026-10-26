import { useState, type FormEvent } from "react";
import { Shield, Lock, Login, UserPlus } from "@nsmr/pixelart-react";
import { api } from "@/lib/api";
import { navigate } from "@/lib/router";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ErrorBox } from "@/components/pixel";
import ShipLaunch from "@/components/ShipLaunch";

export default function Auth({ mode, onDone }: { mode: "login" | "register"; onDone: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const register = mode === "register";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      await api(`/auth/${register ? "register" : "login"}`, {
        method: "POST",
        body: JSON.stringify({ username: form.get("username"), password: form.get("password"), display_name: form.get("display_name") || "" }),
      });
      await onDone();
      navigate(register ? "/settings?welcome=1" : "/bots");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-[calc(100svh-200px)] items-stretch gap-6 lg:grid-cols-[1.1fr_1fr]">
      <div className="pixel-frame relative hidden min-h-[480px] flex-col justify-between overflow-hidden p-6 lg:flex">
        <ShipLaunch className="absolute inset-0" pixel={4} />
        <div className="relative">
          <div className="eyebrow mb-3">登船手续</div>
          <h1 className="m-0 font-pixel text-[36px] leading-[40px] font-normal">
            你的代码。
            <br />
            你的<span className="text-blue">策略实验室</span>。
          </h1>
        </div>
        <ul className="relative m-0 flex list-none flex-col gap-2 p-0">
          {["源码与私人测试按账号隔离", "每个 Bot 在独立进程沙箱中运行", "注册即分配唯一的像素头像，可随时更换"].map((text) => (
            <li key={text} className="flex w-fit items-center gap-2 bg-paper/90 px-2 py-1">
              <Shield size={14} className="text-blue" /> {text}
            </li>
          ))}
        </ul>
      </div>

      <Card className="mx-auto w-full max-w-[440px] gap-5 self-center border border-ink bg-paper-2 py-6">
        <CardHeader className="gap-3 px-6">
          <Tabs value={mode} onValueChange={(v) => navigate(v === "register" ? "/register" : "/login", true)}>
            <TabsList className="w-full">
              <TabsTrigger value="login">
                <Login size={14} /> 登录
              </TabsTrigger>
              <TabsTrigger value="register">
                <UserPlus size={14} /> 注册
              </TabsTrigger>
            </TabsList>
          </Tabs>
          <CardTitle className="text-[24px] leading-[28px] font-normal">{register ? "创建船长账号" : "欢迎回港"}</CardTitle>
          <CardDescription className="text-ink-2">{register ? "注册后即可上传 Bot、提交测试，并获得一枚独一无二的对角对称像素头像。" : "登录后查看自己的版本、任务与对战记录。"}</CardDescription>
        </CardHeader>
        <form onSubmit={submit}>
          <CardContent className="flex flex-col gap-4 px-6">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="username">用户名</Label>
              <Input id="username" name="username" autoComplete="username" required minLength={3} maxLength={32} pattern="[a-zA-Z0-9][a-zA-Z0-9_\-]{2,31}" placeholder="captain_01" />
            </div>
            {register && (
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="display_name">显示名称</Label>
                <Input id="display_name" name="display_name" autoComplete="nickname" maxLength={40} placeholder="排行榜上的名字（可选）" />
              </div>
            )}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="password">密码</Label>
              <Input id="password" name="password" type="password" autoComplete={register ? "new-password" : "current-password"} minLength={register ? 12 : 1} maxLength={128} required placeholder={register ? "至少 12 个字符" : "输入现有密码"} />
            </div>
            <ErrorBox message={error} />
          </CardContent>
          <CardFooter className="mt-5 flex flex-col items-stretch gap-3 px-6">
            <Button size="lg" disabled={busy}>
              <Lock size={16} /> {busy ? "正在处理…" : register ? "创建账号 >" : "登录 >"}
            </Button>
            <p className="m-0 text-ink-3">暂不支持邮箱找回密码，请妥善保存。</p>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
