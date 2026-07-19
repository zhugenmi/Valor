import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import PortfolioForm from "./components/PortfolioForm";
import { usePortfolioStore } from "./store";

export default function PortfolioListPage() {
  const navigate = useNavigate();
  const { list, loading, error, fetchList, remove } = usePortfolioStore();
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  return (
    <div className="mx-auto max-w-4xl p-6">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="font-bold text-2xl">我的组合</h1>
        <Button onClick={() => setShowForm(true)}>
          <Plus className="mr-1 h-4 w-4" /> 新建
        </Button>
      </div>
      {error && <div className="mb-4 text-red-500">{error}</div>}
      {loading && <div className="text-gray-500">加载中...</div>}
      <div className="space-y-3">
        {list.map((p) => (
          <Card
            className="flex cursor-pointer items-center justify-between p-4 hover:shadow-md"
            key={p.portfolio_id}
            onClick={() => navigate(`/portfolio/${p.portfolio_id}`)}
          >
            <div>
              <div className="font-medium text-lg">{p.name}</div>
              <div className="text-gray-500 text-sm">
                基准 {p.benchmark} · 现金 ¥{Number(p.cash).toLocaleString()} ·
                更新 {new Date(p.updated_at).toLocaleString()}
              </div>
            </div>
            <Button
              className="variant-ghost size-icon"
              onClick={(e) => {
                e.stopPropagation();
                if (confirm(`删除组合「${p.name}」？`)) remove(p.portfolio_id);
              }}
            >
              <Trash2 className="h-4 w-4 text-red-500" />
            </Button>
          </Card>
        ))}
        {!loading && list.length === 0 && (
          <div className="py-12 text-center text-gray-500">
            暂无组合，点击「新建」开始
          </div>
        )}
      </div>
      <PortfolioForm
        onClose={() => setShowForm(false)}
        onCreated={(id) => navigate(`/portfolio/${id}`)}
        open={showForm}
      />
    </div>
  );
}
