pragma solidity ^0.8.30;
import {BackupAnchor} from "../src/BackupAnchor.sol";
contract Stranger {
    function attempt(BackupAnchor a) external returns(bool ok) {
        (ok,) = address(a).call(abi.encodeCall(a.commit,(1,1,bytes32(uint256(1)),bytes32(0),bytes32(0))));
    }
}
contract BackupAnchorTest {
    function testLatestAndHistoryAdvance() public {
        BackupAnchor a = new BackupAnchor(keccak256("lab"));
        a.commit(1,3,bytes32(uint256(1)),bytes32(uint256(10)),bytes32(0));
        a.commit(2,5,bytes32(uint256(2)),bytes32(uint256(20)),bytes32(uint256(1)));
        (uint64 epoch,uint64 seq,bytes32 hash,bytes32 head)=a.latest();
        require(epoch==2 && seq==5 && hash==bytes32(uint256(2)) && head==bytes32(uint256(20)));
    }
    function testRejectUnauthorizedStaleAndRollback() public {
        BackupAnchor a=new BackupAnchor(keccak256("lab"));
        require(!new Stranger().attempt(a));
        a.commit(1,3,bytes32(uint256(1)),bytes32(0),bytes32(0));
        (bool ok,)=address(a).call(abi.encodeCall(a.commit,(1,3,bytes32(uint256(2)),bytes32(0),bytes32(uint256(1))))); require(!ok);
        (ok,)=address(a).call(abi.encodeCall(a.commit,(2,2,bytes32(uint256(2)),bytes32(0),bytes32(uint256(1))))); require(!ok);
        (ok,)=address(a).call(abi.encodeCall(a.commit,(2,3,bytes32(uint256(2)),bytes32(0),bytes32(0)))); require(!ok);
    }
}
