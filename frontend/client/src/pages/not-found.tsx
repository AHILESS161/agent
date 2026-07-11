import { Link } from "wouter";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
      <p className="text-6xl font-bold text-muted-foreground/30">404</p>
      <h1 className="text-xl font-bold mt-4">Страница не найдена</h1>
      <p className="text-sm text-muted-foreground mt-2">Запрашиваемая страница не существует или была перемещена</p>
      <Link href="/dashboard">
        <Button variant="outline" className="mt-6" data-testid="button-go-home">
          <ArrowLeft className="w-4 h-4 mr-2" /> На главную
        </Button>
      </Link>
    </div>
  );
}
