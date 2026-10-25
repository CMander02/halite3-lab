// Halite 3 Lab JSON-Lines example. C++17; nlohmann/json is provided by the server.
#include <nlohmann/json.hpp>
#include <algorithm>
#include <array>
#include <iostream>
#include <queue>
#include <set>
#include <sstream>
#include <string>
#include <vector>
using nlohmann::json;
int main(){
 std::string line;
 if(!std::getline(std::cin,line))return 0;
 auto init=json::parse(line);int me=init["player_id"],w=init["width"],h=init["height"];
 auto constants=init["constants"];std::set<int> returning;
 std::cout<<"cpp-greedy"<<std::endl;
 auto index=[&](int x,int y){return ((y+h)%h)*w+(x+w)%w;};
 std::array<char,5> directions={'o','n','s','e','w'};
 std::array<int,5> dx={0,0,0,1,-1},dy={0,-1,1,0,0};
 while(std::getline(std::cin,line)){
  auto obs=json::parse(line);json own;
  for(auto &p:obs["players"])if(p["id"]==me)own=p;
  int home=index(own["factory"][0],own["factory"][1]);
  std::vector<int> dist(w*h,w*h);std::queue<int> queue;dist[home]=0;queue.push(home);
  while(!queue.empty()){int pos=queue.front();queue.pop();for(int d=1;d<5;d++){int n=index(pos%w+dx[d],pos/w+dy[d]);if(obs["terrain"][n]==0 && dist[n]>dist[pos]+1){dist[n]=dist[pos]+1;queue.push(n);}}}
  std::vector<json> ships;std::set<int> reserved,enemies;
  for(auto s:own["ships"]){ships.push_back(s);reserved.insert(index(s["x"],s["y"]));}
  for(auto p:obs["players"])if(p["id"]!=me)for(auto s:p["ships"])enemies.insert(index(s["x"],s["y"]));
  std::sort(ships.begin(),ships.end(),[](auto&a,auto&b){return a["cargo"].template get<int>()>b["cargo"].template get<int>();});
  std::ostringstream commands;
  for(auto s:ships){int id=s["id"],cargo=s["cargo"],x=s["x"],y=s["y"],pos=index(x,y);reserved.erase(pos);
   if(cargo==0)returning.erase(id);
   if(cargo>=650 || constants["MAX_TURNS"].get<int>()-obs["turn"].get<int>()<=dist[pos]+5)returning.insert(id);
   int ground=obs["halite"][pos].is_null()?0:obs["halite"][pos].get<int>();int cost=ground/constants["MOVE_COST_RATIO"].get<int>();
   double best=-1e30;int choice=0,target=pos;
   for(int d=0;d<5;d++){int n=index(x+dx[d],y+dy[d]);if(obs["terrain"][n]!=0 || reserved.count(n) || (d>0 && cargo<cost))continue;
    int resource=obs["halite"][n].is_null()?100:obs["halite"][n].get<int>();
    double score=returning.count(id)?-dist[n]*120.0:(d==0?resource/4.0:resource/6.0-8);
    if(returning.count(id) && n==home)score+=1000;
    if(enemies.count(n))score-=2000;
    if(score>best){best=score;choice=d;target=n;}
   }
   reserved.insert(target);commands<<"m "<<id<<" "<<directions[choice]<<" ";
  }
  if(own["bank"].get<int>()>=constants["NEW_ENTITY_ENERGY_COST"].get<int>() && !reserved.count(home) && ships.size()<8 && obs["turn"].get<int>()<constants["MAX_TURNS"].get<int>()*.5)commands<<"g";
  std::cout<<commands.str()<<std::endl;
 }
}
