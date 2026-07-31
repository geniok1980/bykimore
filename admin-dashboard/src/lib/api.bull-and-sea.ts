import { request } from "./api";

export type BullAndSeaStats = {
  total_pieces: number;
  total_weight_tons: number;
};

export async function getBullAndSeaStats(): Promise<BullAndSeaStats> {
  return request<BullAndSeaStats>(`/bull-and-sea/stats`, { method: "GET" });
}
